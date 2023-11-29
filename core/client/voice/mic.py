import audioop
import os
import random
from collections import deque, namedtuple
from threading import Event, Lock
from time import sleep

import pyaudio
import speech_recognition
from speech_recognition import AudioData, AudioSource, Microphone

from core.audio import wait_while_speaking
from core.configuration import Configuration
from core.util import (
    check_for_signal,
    get_ipc_directory,
    play_wav,
    resolve_resource_file,
)
from core.util.log import LOG
from core.util.metrics import Stopwatch

from .data_structures import CyclicAudioBuffer, RollingMean
from .silence import SilenceDetector, SilenceResultType

WakeWordData = namedtuple("WakeWordData", ["audio", "found", "stopped", "end_audio"])


class MutableStream:
    """
    This class wraps an audio stream from the microphone, allowing it to be muted
    or unmuted.
    It controls the audio input from the Microphone by stopping and starting the stream.

    Attributes:
        wrapped_stream: The original audio stream from the microphone.
        format: The format of the audio stream.
        frames_per_buffer: The number of frames per buffer.
        SAMPLE_WIDTH: The sample width of the audio stream.
        bytes_per_buffer: The number of bytes per buffer.
        muted_buffer: A buffer filled with zero bytes.
        read_lock: A lock for thread-safety while reading from the stream.
        chunk: A chunk of audio data.
        chunk_ready: An event that signals when a chunk is ready to be read.
        muted: A flag indicating whether the stream is currently muted.
        chunk_deque: A deque that holds chunks of audio data.
    """

    def __init__(self, wrapped_stream, format, muted=False, frames_per_buffer=4000):
        assert wrapped_stream is not None
        self.wrapped_stream = wrapped_stream

        self.format = format
        self.frames_per_buffer = frames_per_buffer
        self.SAMPLE_WIDTH = pyaudio.get_sample_size(format)
        self.bytes_per_buffer = self.frames_per_buffer * self.SAMPLE_WIDTH
        self.muted_buffer = b"".join([b"\x00" * self.SAMPLE_WIDTH])
        self.read_lock = Lock()

        self.chunk = bytes(self.bytes_per_buffer)
        self.chunk_ready = Event()
        self.muted = muted

        # The size of this queue is important.
        # Too small, and chunks could be missed.
        # Too large, and there will be a delay in wake word recognition.
        self.chunk_deque = deque(maxlen=8)

        # Begin listening
        self.wrapped_stream.start_stream()

    def mute(self):
        """Stop the stream and set the muted flag."""
        self.muted = True

    def unmute(self):
        """Start the stream and clear the muted flag."""
        self.muted = False

    def iter_chunks(self):
        """Yield chunks of audio data from the deque."""
        # If muted during read return empty buffer. This ensures no
        # reads occur while the stream is stopped
        with self.read_lock:
            while True:
                if self.muted:
                    return self.muted_buffer
                while self.chunk_deque:
                    yield self.chunk_deque.popleft()

                self.chunk_ready.clear()
                self.chunk_ready.wait()

    def read(self, size, of_exc=False):
        """
        Read data from the stream.

        Args:
            size (int): Number of bytes to read.
            of_exc (bool): Flag determining if the audio producer thread should
            throw IOError at overflows.

        Returns:
            bytes: Data read from the device.
        """
        # If muted during read return empty buffer. This ensures no
        # reads occur while the stream is stopped
        if self.muted:
            LOG.debug("returning self.muted_buffer")
            return self.muted_buffer

        frames = deque()
        remaining = size

        for chunk in self.iter_chunks():
            frames.append(chunk)
            remaining -= len(chunk)
            if remaining <= 0:
                break

        input_latency = self.wrapped_stream.get_input_latency()
        if input_latency > 0.2:
            pass
            # LOG.warning("High input latency: %f" % input_latency)
            # LOG.debug("High input latency: %f" % input_latency)
        audio = b"".join(list(frames))
        return audio

    def close(self):
        """Close the wrapped stream."""
        self.wrapped_stream.stop_stream()
        self.wrapped_stream.close()
        self.wrapped_stream = None

    def is_stopped(self):
        """
        Check if the wrapped stream is stopped.

        Returns:
            bool: True if the stream is stopped, False otherwise.
        """
        try:
            return self.wrapped_stream.is_stopped()
        except Exception as e:
            LOG.error(repr(e))
            return True  # Assume the stream has been closed and thusly stopped

    def stop_stream(self):
        """Stop the wrapped stream."""
        return self.wrapped_stream.stop_stream()


class MutableMicrophone(Microphone):
    """
    Parameters:

    device_index: int = None
        Index of input device to use.

    sample_rate: int = 16000
        Sample rate of audio stream.

    chunk_size: int = 160
        Size of each read chunk.

    mute: bool = False
        Whether to start with muted audio stream.

    retry: bool = True
        Whether to retry on microphone errors.
    """

    def __init__(
        self,
        device_index=None,
        sample_rate=16000,
        chunk_size=160,
        mute=False,
        retry=True,
    ):
        Microphone.__init__(
            self,
            device_index=device_index,
            sample_rate=sample_rate,
            chunk_size=chunk_size,
        )
        self.muted = False
        self.retry_on_mic_error = retry
        if mute:
            self.mute()

    def __enter__(self):
        """Start microphone stream. Retries on failure."""
        exit_flag = False
        while not exit_flag:
            try:
                return self._start()
            except Exception as e:
                if not self.retry_on_mic_error:
                    raise e
                LOG.exception("Can't start mic!")
            sleep(1)

    def _stream_callback(self, in_data, frame_count, time_info, status):
        """Callback from pyaudio.

        Rather than buffer chunks, we simply assigned the current chunk to the
        class instance and signal that it's ready.
        """
        self.stream.chunk_deque.append(in_data)
        self.stream.chunk_ready.set()
        return (None, pyaudio.paContinue)

    def _start(self):
        """Open the selected device and setup the stream."""
        assert (
            self.stream is None
        ), "This audio source is already inside a context manager"
        self.audio = pyaudio.PyAudio()

        wrapped_stream = self.audio.open(
            input_device_index=self.device_index,
            channels=1,
            format=self.format,
            rate=self.SAMPLE_RATE,
            frames_per_buffer=self.CHUNK,
            stream_callback=self._stream_callback,
            input=True,  # stream is an input stream
        )

        self.stream = MutableStream(
            wrapped_stream=wrapped_stream,
            format=self.format,
            muted=self.muted,
            frames_per_buffer=self.CHUNK,
        )

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._stop()

    def _stop(self):
        """Stop and close an open stream."""
        try:
            if not self.stream.is_stopped():
                self.stream.stop_stream()
            self.stream.close()
        except Exception:
            LOG.exception("Failed to stop mic input stream")
            # Let's pretend nothing is wrong...

        self.stream = None
        self.audio.terminate()

    def restart(self):
        """Shutdown input device and restart."""
        self._stop()
        self._start()

    def mute(self):
        self.muted = True
        LOG.debug("muting microphone...")
        if self.stream:
            self.stream.mute()

    def unmute(self):
        self.muted = False
        LOG.debug("unmuting microphone...")
        if self.stream:
            self.stream.unmute()

    def is_muted(self):
        return self.muted

    def duration_to_bytes(self, sec):
        """Converts a duration in seconds to number of recorded bytes.

        Args:
            sec: number of seconds

        Returns:
            (int) equivalent number of bytes recorded by this Mic
        """
        return int(sec * self.SAMPLE_RATE) * self.SAMPLE_WIDTH


def get_silence(num_bytes):
    return b"\0" * num_bytes


class ResponsiveRecognizer(speech_recognition.Recognizer):
    """
    The ResponsiveRecognizer class extends the Recognizer class from the
    speech_recognition module. It is designed to continuously listen for audio
    input and perform actions when certain audio patterns are recognized. This
    class is primarily used for wake word detection and subsequent command
    recognition.

    Attributes:
        SILENCE_SEC: Padding of silence when feeding to pocketsphinx.
        MIN_LOUD_SEC_PER_PHRASE: The minimum seconds of noise before a phrase
        can be considered complete.
        MIN_SILENCE_AT_END: The minimum seconds of silence required at the end
        before a phrase will be considered complete.
        SEC_BETWEEN_WW_CHECKS: Time between pocketsphinx checks for the wake word.
        _watchdog: A function to be called periodically during long operations.
        config: Configuration settings.
        upload_url: URL for uploading wake word samples.
        upload_disabled: Flag indicating whether wake word sample uploading is
        disabled.
        wake_word_name: The name of the wake word to be recognized.
        overflow_exc: Flag indicating whether to throw an exception on audio
        buffer overflow.
        wake_word_recognizer: The wake word recognizer instance.
        audio: The PyAudio instance.
        multiplier: The energy level multiplier for adjusting the energy
        threshold for silence detection.
        energy_ratio: The energy ratio for adjusting the energy threshold for
        silence detection.
        mic_level_file: The file path for the microphone level file.
        _stop_signaled: Flag indicating whether a stop signal has been received.
        _listen_triggered: Flag indicating whether listening has been triggered.
        _stop_recording: Flag indicating whether to stop recording.
        recording_timeout: The maximum seconds a phrase can be recorded,
        provided there is noise the entire time.
        recording_timeout_with_silence: The maximum time it will continue to
        record silence when not enough noise has been detected.
        silence_detector: The silence detector instance.
    """

    # Padding of silence when feeding to pocketsphinx
    SILENCE_SEC = 0.01

    # The minimum seconds of noise before a
    # phrase can be considered complete
    MIN_LOUD_SEC_PER_PHRASE = 0.5

    # The minimum seconds of silence required at the end
    # before a phrase will be considered complete
    MIN_SILENCE_AT_END = 0.25

    # Time between pocketsphinx checks for the wake word
    SEC_BETWEEN_WW_CHECKS = 0.2

    def __init__(self, wake_word_recognizer, watchdog=None):
        """
        Initializes a new instance of the ResponsiveRecognizer class.

        Args:
            wake_word_recognizer: The wake word recognizer instance.
            watchdog: A function to be called periodically during long operations.
        """
        self._watchdog = watchdog or (lambda: None)  # Default to dummy func
        self.config = Configuration.get()
        listener_config = self.config.get("listener")
        self.upload_url = listener_config["wake_word_upload"]["url"]
        self.upload_disabled = listener_config["wake_word_upload"]["disable"]
        self.wake_word_name = wake_word_recognizer.key_phrase

        self.overflow_exc = listener_config.get("overflow_exception", False)

        super().__init__()
        self.wake_word_recognizer = wake_word_recognizer
        self.audio = pyaudio.PyAudio()
        self.multiplier = listener_config.get("multiplier")
        self.energy_ratio = listener_config.get("energy_ratio")

        self.mic_level_file = os.path.join(get_ipc_directory(), "mic_level")

        # Signal statuses
        self._stop_signaled = False
        self._listen_triggered = False
        self._stop_recording = False

        # The maximum seconds a phrase can be recorded,
        # provided there is noise the entire time
        # Get recording timeout value
        self.recording_timeout = listener_config.get("recording_timeout", 10.0)
        vad_config = listener_config.get("VAD", {})
        LOG.debug(
            "the set silence duration: " + repr(vad_config.get("silence_seconds"))
        )

        self.silence_detector = SilenceDetector(
            speech_seconds=vad_config.get("speech_seconds", 0.1),
            silence_seconds=vad_config.get("silence_seconds", 0.5),
            min_seconds=vad_config.get("min_seconds", 1),
            # NOTE: set to none for infinite reccording if speech continues
            max_seconds=None,
            before_seconds=vad_config.get("before_seconds", 0.5),
            current_energy_threshold=vad_config.get("initial_energy_threshold", 1000.0),
            max_current_ratio_threshold=vad_config.get(
                "max_current_ratio_threshold", 2
            ),
            vad_config=vad_config,
        )

    def record_sound_chunk(self, source):
        """
        Records a chunk of sound from the specified source.

        Args:
            source: The AudioSource instance to record from.

        Returns:
            The recorded sound chunk.
        """
        return source.stream.read(source.CHUNK, self.overflow_exc)

    @staticmethod
    def calc_energy(sound_chunk, sample_width):
        """
        Calculates the energy (loudness) of the specified sound chunk.

        Args:
            sound_chunk: The sound chunk to calculate the energy of.
            sample_width: The sample width of the sound chunk.

        Returns:
            The calculated energy of the sound chunk.
        """
        return audioop.rms(sound_chunk, sample_width)

    def _record_phrase(
        self,
        source: AudioSource,
        sec_per_buffer: float,
        stream=None,
        ww_frames: deque = None,
    ) -> bytearray:
        """
        Records an entire spoken phrase.

        This method waits for a period of silence and then returns the audio.
        If silence isn't detected, it will terminate and return a buffer of
        self.recording_timeout duration.

        Args:
            source (AudioSource):  Source producing the audio chunks.
            sec_per_buffer (float):  Fractional number of seconds in each chunk.
            stream (AudioStreamHandler): Stream target that will receive chunks of the
            utterance audio while it is being recorded.
            ww_frames (deque):  Frames of audio data from the last part of wake word
            detection.

        Returns:
            bytearray: Complete audio buffer recorded, including any silence at the end
            of the user's utterance.
        """

        # Maximum number of chunks to record before timing out
        # int(self.recording_timeout / sec_per_buffer)

        num_chunks = 0

        # bytearray to store audio in, initialized with a single sample of
        # silence.
        # byte_data = get_silence(source.SAMPLE_WIDTH)

        self.silence_detector.start()
        if stream:
            stream.stream_start()

        stopwatch = Stopwatch()
        with stopwatch:
            for chunk in source.stream.iter_chunks():
                if self._stop_recording or check_for_signal("buttonPress"):
                    break

                result = self.silence_detector.process(chunk)

                if result.type in {
                    SilenceResultType.SPEECH,
                    SilenceResultType.PHRASE_START,
                }:
                    # LOG.debug("voice recognition state: " + repr(result.type))
                    # NOTE: ensures streamed chunk only gets audiodata with speech for
                    # transcription
                    stopwatch.lap()
                    if stream:
                        stream.stream_chunk(chunk)

                if result.type in {
                    SilenceResultType.PHRASE_END,
                    SilenceResultType.TIMEOUT,
                }:
                    LOG.debug("voice recognition state: " + repr(result.type))
                    break
                # Periodically write the energy level to the mic level file.
                if num_chunks % 10 == 0:
                    self._watchdog()
                    self.write_mic_level(result.energy, source)
                num_chunks += 1

        LOG.debug("The recorded silence duration is: " + str(stopwatch))
        # return audio_data
        return self.silence_detector.stop()

    def write_mic_level(self, energy, source):
        """
        Writes the microphone level to the file log.

        Args:
            energy: The energy level to write.
            source: The AudioSource instance.
        """
        with open(self.mic_level_file, "w") as f:
            f.write(
                "Energy:  cur={} thresh={:.3f} muted={}".format(
                    energy, self.energy_threshold, int(source.muted)
                )
            )

    def _skip_wake_word(self):
        """
        Checks if the program is told to skip the wake word.

        This can happen, for example, when we are in a dialog with the user.

        Returns:
            True if the wake word should be skipped, False otherwise.
        """
        if self._listen_triggered:
            return True

        # Pressing the Mark 1 button can start recording (unless
        # it is being used to mean 'stop' instead)
        if check_for_signal("buttonPress", 1):
            # give other processes time to consume this signal if
            # it was meant to be a 'stop'
            sleep(0.25)
            if check_for_signal("buttonPress"):
                # Signal is still here, assume it was intended to
                # begin recording
                LOG.debug("Button Pressed, wakeword not needed")
                return True

        return False

    def stop(self):
        """
        Signals to stop and exit the waiting state.
        """
        self._stop_signaled = True
        self._stop_recording = True

    def trigger_listen(self):
        """
        Externally triggers listening.
        """
        LOG.debug("Listen triggered from external source.")
        self._listen_triggered = True

    def _handle_wakeword_found(self, audio_data, source, emitter):
        """
        Performs actions to be triggered after a wake word is found.

        This includes: emit event on messagebus that a wake word is heard,
        store wake word to disk if configured and sending the wake word data
        to the cloud in case the user has opted into the data sharing.

        Args:
            audio_data: The audio data containing the wake word.
            source: The AudioSource instance.
            emitter: The EventEmitter instance.
        """
        emitter.emit("recognizer_loop:wakeword")

    def _wait_until_wake_word(
        self, source: AudioSource, sec_per_buffer: float
    ) -> WakeWordData:
        """
        Listens continuously on source until a wake word is spoken.

        Args:
            source (AudioSource):  Source producing the audio chunks.
            sec_per_buffer (float):  Fractional number of seconds in each chunk.

        Returns:
            WakeWordData: A named tuple containing the audio data, a boolean indicating
            if the wake word was found, a boolean indicating if the stop signal was
            received, and the end audio frames.

        """

        # The maximum audio in seconds to keep for transcribing a phrase
        # The wake word must fit in this time
        ww_duration = self.wake_word_recognizer.expected_duration
        ww_test_duration = max(3, ww_duration)

        mic_write_counter = 0
        num_silent_bytes = int(
            self.SILENCE_SEC * source.SAMPLE_RATE * source.SAMPLE_WIDTH
        )

        silence = get_silence(num_silent_bytes)

        # Max bytes for byte_data before audio is removed from the front
        max_size = source.duration_to_bytes(ww_duration)
        test_size = source.duration_to_bytes(ww_test_duration)
        audio_buffer = CyclicAudioBuffer(max_size, silence)

        buffers_per_check = self.SEC_BETWEEN_WW_CHECKS / sec_per_buffer
        buffers_since_check = 0.0

        # Rolling buffer to track the audio energy (loudness) heard on
        # the source recently.  An average audio energy is maintained
        # based on these levels.
        average_samples = int(5 / sec_per_buffer)  # average over last 5 secs
        audio_mean = RollingMean(average_samples)

        # These are frames immediately after wake word is detected
        # that we want to keep to send to STT
        ww_frames = deque(maxlen=7)

        said_wake_word = False
        audio_data = silence

        # NOTE: this should only be used if an event wants to detect user speech to
        # avoid too much resources used for real-time speech detection
        # self.silence_detector.start()
        # counter = 0
        while not said_wake_word and not self._stop_signaled:
            for chunk in source.stream.iter_chunks():
                if self._skip_wake_word():
                    return WakeWordData(
                        audio_data, False, self._stop_signaled, ww_frames
                    )

                # chunk = self.record_sound_chunk(source)
                audio_buffer.append(chunk)
                ww_frames.append(chunk)
                # HACK: for detecting silence
                # result = self.silence_detector.process(chunk)
                #
                # if result.type == SilenceResultType.SPEECH:
                #     # Continue processing chunks while speech is detected
                #     # NOTE: assuming a count is in deci seconds,
                #
                #     counter += 1
                #     # LOG.debug(
                #     #     "result of speech when waiting for wakeword"
                #     #     + repr(result)
                #     #     + "and counter value: "
                #     #     + repr(counter)
                #     # )
                #     if counter == 40:
                #         LOG.info("Speech detected")
                #         counter = 0
                # elif result.type == SilenceResultType.PHRASE_END:
                #     counter = 0

                buffers_since_check += 1.0

                # if self.loop
                energy = self.calc_energy(chunk, source.SAMPLE_WIDTH)
                audio_mean.append_sample(energy)

                if energy < self.energy_threshold * self.multiplier:
                    self._adjust_threshold(energy, sec_per_buffer)
                # maintain the threshold using average
                if self.energy_threshold < energy < audio_mean.value * 1.5:
                    # bump the threshold to just above this value
                    self.energy_threshold = energy * 1.2

                # Periodically output energy level stats. This can be used to
                # visualize the microphone input, e.g. a needle on a meter.
                if mic_write_counter % 3:
                    self._watchdog()
                    self.write_mic_level(energy, source)
                mic_write_counter += 1

                # buffers_since_check += 1.0
                # Send chunk to wake_word_recognizer
                self.wake_word_recognizer.update(chunk)

                if buffers_since_check > buffers_per_check:
                    buffers_since_check -= buffers_per_check
                    audio_data = audio_buffer.get_last(test_size) + silence
                    said_wake_word = self.wake_word_recognizer.found_wake_word(
                        audio_data
                    )
                if said_wake_word:
                    return WakeWordData(
                        audio_data, said_wake_word, self._stop_signaled, ww_frames
                    )

    @staticmethod
    def _create_audio_data(raw_data, source):
        """
        Constructs an AudioData instance with the same parameters as
        the source and the specified frame_data.

        Args:
            raw_data: The raw audio data.
            source: The AudioSource instance.

        Returns:
            An AudioData instance.
        """
        return AudioData(raw_data, source.SAMPLE_RATE, source.SAMPLE_WIDTH)

    # TODO: seperate activation sound from start_listening
    def mute_and_confirm_listening(self, source):
        """
        Mutes the source and plays a confirmation sound indicating
        that the system is listening.

        Args:
            source: The AudioSource instance.

        Returns:
            True if a confirmation sound was played, False otherwise.
        """
        if self._skip_wake_word():
            audio_file = resolve_resource_file(
                self.config.get("sounds").get("activation_sound")
            )
            self._listen_triggered = False
        else:
            tts = self.config.get("sounds").get("start_listening")
            audio_file = resolve_resource_file(
                random.choice(self.config.get("sounds").get(tts))
            )
        LOG.info(audio_file)
        if audio_file:
            source.mute()
            play_wav(audio_file).wait()
            source.unmute()
            return True
        else:
            return False

    def play_end_listening_sound(self, source):
        if self.config.get("confirm_listening_end"):
            audio_file = resolve_resource_file(
                self.config.get("sounds").get("end_sound")
            )
            LOG.info(audio_file)
            source.mute()
            play_wav(audio_file).wait()
            source.unmute()

    def listen(
        self,
        source: AudioSource,
        emitter,
        stream=None,
    ) -> AudioData:
        """
        Listens for chunks of audio that STT can be performed on.

        This method will listen continuously for a wake-up-word, then return the
        audio chunk containing the spoken phrase that comes immediately afterwards.

        Args:
            source (AudioSource):  Source producing the audio chunks.
            emitter (EventEmitter): Emitter for notifications of when recording
            begins and ends.
            stream (AudioStreamHandler): Stream target that will receive chunks
            of the utterance audio while it is being recorded.

        Returns:
            AudioData: Audio with the user's utterance, minus the wake-up-word.
        """
        assert isinstance(source, AudioSource), "Source must be an AudioSource"

        # self.record_sound_chunk()
        # bytes_per_sec = source.SAMPLE_RATE * source.SAMPLE_WIDTH
        sec_per_buffer = float(source.CHUNK) / source.SAMPLE_RATE

        # Every time a new 'listen()' request begins, reset the threshold
        # used for silence detection.  This is as good of a reset point as
        # any, as we expect the user and system to not be talking.
        # NOTE: adjust_for_ambient_noise() doc claims it will stop early if
        #       speech is detected, but there is no code to actually do that.
        self.adjust_for_ambient_noise(source, 0.3)

        self._stop_recording = False

        LOG.debug("Waiting for wake word...")
        ww_data = self._wait_until_wake_word(source, sec_per_buffer)

        ww_frames = None
        if ww_data.found:
            self._handle_wakeword_found(ww_data.audio, source, emitter)
            ww_frames = ww_data.end_audio
        if ww_data.stopped:
            # If the waiting returned from a stop signal
            return None

        LOG.debug("Recording...")
        # If enabled, play a wave file with a short sound to audibly
        # indicate recording has begun.
        if self.config.get("confirm_listening"):
            # NOTE: Aim is to avoid interference of the activation
            # sound with system speech
            wait_while_speaking()
            if self.mute_and_confirm_listening(source):
                # Clear frames from wakeword detections since they're
                # irrelevant after mute - play wav - unmute sequence
                ww_frames = None

        # Notify system of recording start
        emitter.emit("recognizer_loop:record_begin")

        frame_data = self._record_phrase(source, sec_per_buffer, stream, ww_frames)
        audio_data = self._create_audio_data(frame_data, source)
        emitter.emit("recognizer_loop:record_end")

        # Play a wav file to indicate audio recording has ended
        self.play_end_listening_sound(source)

        return audio_data

    def _adjust_threshold(self, energy, seconds_per_buffer):
        if self.dynamic_energy_threshold and energy > 0:
            # account for different chunk sizes and rates
            damping = self.dynamic_energy_adjustment_damping**seconds_per_buffer
            target_energy = energy * self.energy_ratio
            self.energy_threshold = self.energy_threshold * damping + target_energy * (
                1 - damping
            )
