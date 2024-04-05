import json
import time
from copy import deepcopy
from queue import Empty, Queue
from threading import Lock, Thread

import pyaudio
import speech_recognition as sr
from pyee import EventEmitter
from requests import RequestException
from requests.exceptions import ConnectionError

from source.client.listener.hotword_factory import HotWordFactory
from source.client.listener.mic import MutableMicrophone, ResponsiveRecognizer
from source.configuration import Configuration
from source.stt import STTFactory
from source.util import connected_to_the_internet, find_input_device
from source.util.log import LOG
from source.util.metrics import Stopwatch

MAX_MIC_RESTARTS = 20


AUDIO_DATA = 0
STREAM_START = 1
STREAM_DATA = 2
STREAM_STOP = 3


class AudioStreamHandler(object):
    """
    Handles the audio stream by putting the stream data into a queue.
    The queue is used to manage the audio data in a thread-safe manner.
    """

    def __init__(self, queue):
        """
        Initializes the AudioStreamHandler with a queue.
        :param queue: The queue to put the audio data into.
        """
        self.queue = queue

    def stream_start(self):
        """
        Puts the STREAM_START signal into the queue.
        """
        LOG.debug("SENDING STREAM_START signal")
        self.queue.put((STREAM_START, None))

    def stream_chunk(self, chunk):
        """
        Puts a chunk of the audio stream into the queue.
        :param chunk: A chunk of the audio stream.
        """
        self.queue.put((STREAM_DATA, chunk))

    def stream_stop(self):
        """
        Puts the STREAM_STOP signal into the queue.
        """
        LOG.debug("SENDING STREAM_STOP signal")
        self.queue.put((STREAM_STOP, None))


class AudioProducer(Thread):
    """AudioProducer
    Given a mic and a recognizer implementation, continuously listens to the
    mic for potential speech chunks and pushes them onto the queue.
    """

    def __init__(self, state, queue, mic, recognizer, emitter, stream_handler):
        """
        Initializes the AudioProducer with the given parameters.
        :param state: The state of the RecognizerLoop.
        :param queue: The queue to push speech chunks onto.
        :param mic: The microphone to listen to.
        :param recognizer: The speech recognizer implementation.
        :param emitter: The event emitter.
        :param stream_handler: The audio stream handler.
        """
        super(AudioProducer, self).__init__()
        self.daemon = True
        self.state = state
        self.queue = queue
        self.mic = mic
        self.recognizer = recognizer
        self.emitter = emitter
        self.stream_handler = stream_handler
        # if self.recognizer.can_stream:
        #     self.stream_handler = AudioStreamHandler(self.queue)

    def run(self):
        restart_attempts = 0
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source)
            while self.state.running:
                try:
                    LOG.debug("AUDIO PRODUCER RUNNING")

                    # NOTE: why return full audio when we can return while speech is
                    # made?
                    audio = self.recognizer.listen(
                        source, self.emitter, self.stream_handler
                    )

                    # NOTE: from ignorance I'd say this is a fallback if streaming
                    # doesn't work
                    if audio is not None:
                        self.queue.put((AUDIO_DATA, audio))
                    else:
                        LOG.warning("Audio contains no data.")
                except IOError as e:
                    # IOError will be thrown if the read is unsuccessful.
                    # If self.recognizer.overflow_exc is False (default)
                    # input buffer overflow IOErrors due to not consuming the
                    # buffers quickly enough will be silently ignored.
                    LOG.exception("IOError Exception in AudioProducer")
                    if e.errno == pyaudio.paInputOverflowed:
                        pass  # Ignore overflow errors
                    elif restart_attempts < MAX_MIC_RESTARTS:
                        # restart the mic
                        restart_attempts += 1
                        LOG.info("Restarting the microphone...")
                        source.restart()
                        LOG.info("Restarted...")
                    else:
                        LOG.error("Restarting mic doesn't seem to work. " "Stopping...")
                        raise
                except Exception:
                    LOG.exception("Exception in AudioProducer")
                    # raise
                    if restart_attempts < MAX_MIC_RESTARTS:
                        restart_attempts += 1
                        LOG.info("Restarting the AudioProducer...")
                        time.sleep(1)  # Wait a bit before restarting
                    else:
                        LOG.error("Restarting AudioProducer doesn't seem to work. " "Stopping...")
                        self.state.running = False
                else:
                    # Reset restart attempt counter on successful audio read
                    restart_attempts = 0
                # NOTE: should stream be stopped here
                finally:
                    if self.stream_handler is not None:
                        self.stream_handler.stream_stop()
            LOG.debug("STOPPING PRODUCER LOOP")

    def stop(self):
        """Stop producer thread."""
        self.state.running = False
        self.recognizer.stop()


class AudioConsumer(Thread):
    """AudioConsumer
    Consumes AudioData chunks off the queue
    Args:
            state (RecognizerLoopState): The state of the RecognizerLoop.
            queue (Queue): The queue to consume AudioData chunks from.
            emitter (EventEmitter): The event emitter.
            stt (SpeechToText): The speech-to-text engine.
            wakeup_recognizer (WakeupRecognizer): The wake-up word recognizer.
            wakeword_recognizer (WakeWordRecognizer): The wake word recognizer.
    """

    # In seconds, the minimum audio size to be sent to remote STT
    MIN_AUDIO_SIZE = 0.5

    def __init__(
        self, state, queue, emitter, stt, wakeup_recognizer, wakeword_recognizer
    ):
        super(AudioConsumer, self).__init__()
        self.daemon = True
        self.state = state
        self.queue = queue
        self.emitter = emitter
        self.stt = stt
        self.wakeup_recognizer = wakeup_recognizer
        self.wakeword_recognizer = wakeword_recognizer
        self.transcription = None

    def run(self):
        LOG.debug("AUDIO CONSUMER RUNNING")
        while self.state.running:
            self.read()
        LOG.debug("AUDIO CONSUMER STOPPING")

    def read(self):
        try:
            message = self.queue.get(timeout=0.5)

        except Empty:
            return

        if message is None:
            return

        tag, data = message

        if tag == AUDIO_DATA:
            if data is not None:
                # self.stt.execute(data)
                if self.state.sleeping:
                    self.wake_up(data)
                else:
                    self.process(data)
        elif tag == STREAM_START:
            self.stt.stream_start()
        elif tag == STREAM_DATA:
            self.stt.stream_data(data)

        elif tag == STREAM_STOP:
            self.transcription = self.stt.stream_stop()
            payload = {
                "utterances": [self.transcription],
                "lang": self.stt.lang,
            }
            self.emitter.emit("recognizer_loop:utterance", payload)

        else:
            # LOG.error("Unknown audio queue type %r" % message)
            LOG.error("Unknown audio queue type {}".format(tag))

    def wake_up(self, audio):
        if self.wakeup_recognizer.found_wake_word(audio.frame_data):
            self.state.sleeping = False
            self.emitter.emit("recognizer_loop:awoken")

    @staticmethod
    def _audio_length(audio):
        return float(len(audio.frame_data)) / (audio.sample_rate * audio.sample_width)

    def process(self, audio):
        if self._audio_length(audio) >= self.MIN_AUDIO_SIZE:
            stopwatch = Stopwatch()
            with stopwatch:
                transcription = self.transcribe(audio)
            if transcription:
                ident = str(stopwatch.timestamp) + str(hash(transcription))
                # STT succeeded, send the transcribed speech on for processing
                payload = {
                    "utterances": [transcription],
                    "lang": self.stt.lang,
                    "ident": ident,
                }
                if self.state.running:
                    self.emitter.emit("recognizer_loop:utterance", payload)

            else:
                ident = str(stopwatch.timestamp)
        else:
            LOG.warning("Audio too short to be processed")
            # self.__speak("Didn't get that. Could you repeat it?")
            # self.send_unknown_intent()

    def transcribe(self, audio):
        try:
            # Invoke the STT engine on the audio clip
            stopwatch = Stopwatch()
            with stopwatch:
                text = self.stt.execute(audio)
            LOG.info("TIME TO TRANSCRIBE SPEECH: " + str(stopwatch))
            if text is not None:
                LOG.info("STT: " + text)
            else:
                self.send_unknown_intent()
                LOG.info("no words were transcribed")
            return text

        except sr.RequestError as e:
            LOG.error("Could not request Speech Recognition {0}".format(e))
        except ConnectionError as e:
            LOG.error("Connection Error: {0}".format(e))

            self.emitter.emit("recognizer_loop:no_internet")
        except RequestException as e:
            LOG.error(e.__class__.__name__ + ": " + str(e))
        except Exception as e:
            self.send_unknown_intent()
            LOG.error(e)
            LOG.error("Speech Recognition could not understand audio")
            return None

        if not connected_to_the_internet():
            dialog_name = "not_connected_to_the_internet"
            self.__speak(dialog_name)

    def __speak(self, utterance):
        payload = {"utterance": utterance}
        self.emitter.emit("speak", payload)

    def send_unknown_intent(self):
        """Send message that nothing was transcribed."""
        self.emitter.emit("recognizer_loop:speech.recognition.unknown")

    def stop(self):
        """Stop consumer thread."""
        self.state.running = False

class ListenerLoopState:
    def __init__(self):
        self.running = False
        self.sleeping = False


def recognizer_conf_hash(config):
    """Hash of the values important to the listener."""
    c = {
        "listener": config.get("listener"),
        "hotwords": config.get("hotwords"),
        "stt": config.get("stt"),
        "lang": config.get("lang"),
        "confirm_listening": config.get("confirm_listening"),
        "confirm_listening_end": config.get("confirm_listening_end"),
    }
    return hash(json.dumps(c, sort_keys=True))


class ListenerLoop(EventEmitter):
    """EventEmitter loop running speech recognition.

    Local wake word recognizer and remote general speech recognition.

    Args:
        watchdog: (callable) function to call periodically indicating
                  operational status.
    """

    def __init__(self, watchdog=None, stt=None):
        super(ListenerLoop, self).__init__()
        self._watchdog = watchdog
        self.mute_calls = 0
        self.lock = Lock()
        self.stt = stt
        self.queue = None
        self._load_config()

    def _load_config(self):
        """Load configuration parameters from configuration."""
        config = Configuration.get()["voice"]
        self.config_core = config
        self._config_hash = recognizer_conf_hash(config)
        self.lang = config.get("lang")
        self.config = config.get("listener")
        rate = self.config.get("sample_rate")

        device_index = self.config.get("device_index")
        device_name = self.config.get("device_name")
        if not device_index and device_name:
            device_index = find_input_device(device_name)

        LOG.debug("Using microphone (None = default): " + str(device_index))

        self.microphone = MutableMicrophone(
            device_index, rate, mute=self.mute_calls > 0
        )

        self.wakeword_recognizer = self.create_wake_word_recognizer()
        # TODO - localization
        # self.wakeup_recognizer = self.create_wakeup_recognizer()
        self.wakeup_recognizer = None
        self.responsive_recognizer = ResponsiveRecognizer(
            self.wakeword_recognizer, self._watchdog
        )
        self.state = ListenerLoopState()

    def create_wake_word_recognizer(self):
        """Create a local recognizer to hear the wakeup word

        For example 'Hey Mycroft'.

        The method uses the hotword entry for the selected wakeword, if
        one is missing it will fall back to the old phoneme and threshold in
        the listener entry in the config.

        If the hotword entry doesn't include phoneme and threshold values these
        will be patched in using the defaults from the config listnere entry.
        """
        LOG.info("Creating wake word engine")
        word = self.config.get("wake_word", "hey mycroft")

        # Since we're editing it for server backwards compatibility
        # use a copy so we don't alter the hash of the config and
        # trigger a reload.
        config = deepcopy(self.config_core.get("hotwords", {}))
        return HotWordFactory.create_hotword(word, config, self.lang, loop=self)

    def create_wakeup_recognizer(self):
        LOG.debug("creating stand up word engine")
        word = self.config.get("stand_up_word", "wake up")
        return HotWordFactory.create_hotword(word, lang=self.lang, loop=self)

    def start_async(self):
        """Start consumer and producer threads."""
        LOG.debug("Starting Asynchronous Listener threads")
        self.state.running = True
        stt = STTFactory.create()
        queue = Queue()
        stream_handler = None

        self.producer = AudioProducer(
            self.state,
            queue,
            self.microphone,
            self.responsive_recognizer,
            self,
            stream_handler,
        )
        self.producer.start()
        self.consumer = AudioConsumer(
            self.state,
            queue,
            self,
            stt,
            self.wakeup_recognizer,
            self.wakeword_recognizer,
        )
        self.consumer.start()

    def mute(self):
        """Mute microphone and increase number of requests to mute."""
        self.mute_calls += 1
        if self.microphone:
            self.microphone.mute()

    def unmute(self):
        """Unmute mic if as many unmute calls as mute calls have been received."""
        if self.mute_calls > 0:
            self.mute_calls -= 1

        if self.mute_calls <= 0 and self.microphone:
            self.microphone.unmute()
            self.mute_calls = 0

    def force_unmute(self):
        """Completely unmute mic regardless of the number of calls to mute."""
        self.mute_calls = 0
        self.unmute()

    def is_muted(self):
        if self.microphone:
            return self.microphone.is_muted()
        else:
            return True  # consider 'no mic' muted

    def sleep(self):
        self.state.sleeping = True

    def awaken(self):
        self.state.sleeping = False

    def run(self):
        """Start and reload mic and STT handling threads as needed.

        Wait for KeyboardInterrupt and shutdown cleanly.
        """
        try:
            self.start_async()
        except Exception:
            LOG.exception("Starting producer/consumer threads for listener " "failed.")
            return

        # Handle reload of consumer / producer if config changes
        while self.state.running:
            try:
                time.sleep(1)
                current_hash = recognizer_conf_hash(
                    Configuration().get().get("voice", {})
                )
                if current_hash != self._config_hash:
                    self._config_hash = current_hash
                    LOG.info("Voice: Config has changed, reloading...")
                    self.reload()
            except KeyboardInterrupt as e:
                LOG.error(e)
                self.stop()
                raise  # Re-raise KeyboardInterrupt
            except Exception:
                LOG.exception("Exception in RecognizerLoop")
                raise

    def reload(self):
        """Reload configuration and restart consumer and producer."""
        # with self.lock:
        try:
            self.stop()
            self.wakeword_recognizer.stop()
            # load config
            self._load_config()
            # restart
            self.start_async()

        except Exception as e:
            LOG.error("Failed to reload: " + repr(e))

    def stop(self):
        self.state.running = False
        self.producer.stop()
        self.consumer.stop()
        # wait for threads to shutdown
        self.producer.join()
        self.consumer.join()
