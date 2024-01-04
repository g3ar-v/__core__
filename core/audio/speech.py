import re
import time
from threading import Lock

from core.configuration import Configuration
from core.llm import LLM
from core.messagebus.message import Message
from core.tts import TTSFactory

# from core.tts.remote_tts import RemoteTTSException
from core.tts.mimic3_tts import Mimic3
from core.util import check_for_signal, create_signal
from core.util.log import LOG
from core.util.metrics import Stopwatch
from core.util.network_utils import InternetDown

bus = None  # messagebus connection
config = None
tts = None
tts_hash = None
llm = LLM(bus)
lock = Lock()
mimic_fallback_obj = None

_last_stop_signal = 0
interrupted_utterance = None


def handle_speak(event):
    """Handle "speak" message

    Parse sentences and invoke text to speech service.
    """
    config = Configuration.get()
    Configuration.set_config_update_handlers(bus)
    global _last_stop_signal
    # if the message is targeted and audio is not the target don't
    # don't synthezise speech
    event.context = event.context or {}
    if event.context.get("destination") and not (
        "debug_cli" in event.context["destination"]
        or "audio" in event.context["destination"]
    ):
        return

    # Get conversation ID
    if event.context and "ident" in event.context:
        ident = event.context["ident"]
    else:
        ident = "unknown"

    # start = time.time()  # Time of speech request
    with lock:
        stopwatch = Stopwatch()
        stopwatch.start()
        utterance = event.data["utterance"]
        listen = event.data.get("expect_response", False)

        # NOTE: removed ai messages from here and kept in qa service. To prevent
        # tracking all system messages
        LOG.info(f"Speaking utterance: {utterance}")
        # if llm.message_history:
        #     llm.message_history.add_ai_message(utterance)
        # HACK: is there an efficient way of getting the previous utterance?
        global interrupted_utterance
        interrupted_utterance = utterance
        speak(utterance, ident, listen)

        stopwatch.stop()


def speak(utterance, ident, listen=False):
    """start speaking the utterance using selected tts backend.

    Args:
        utterance:  The sentence to be spoken
        ident:      Ident tying the utterance to the source query
    """
    global tts_hash
    # update TTS object if configuration has changed
    if tts_hash != hash(str(config.get("tts", ""))):
        global tts
        # Create new tts instance
        if tts:
            tts.playback.detach_tts(tts)
        tts = TTSFactory.create()
        tts.init(bus)
        tts_hash = hash(str(config.get("tts", "")))

    # NOTE: Only elevenlabs supports streaming for now so if the conditions are not met
    # don't stream just generate audio file and play
    if (
        config.get("Audio", {}).get("stream_tts", {})
        and tts.tts_name == "ElevenLabsTTS"
    ):
        LOG.debug("Streaming Audio")
        create_signal("isSpeaking")
        tts.begin_audio()
        tts.stream_tts(utterance)
        tts.end_audio(listen)
        check_for_signal("isSpeaking")
    else:
        try:
            tts.execute(utterance, ident, listen)
        except Exception as e:
            mimic_fallback_tts(utterance, ident, listen)
            LOG.error(e)
            # LOG.exception("TTS execution failed.")


def _get_mimic_fallback():
    """Lazily initializes the fallback TTS if needed."""
    global mimic_fallback_obj
    if not mimic_fallback_obj:
        config = Configuration.get()
        tts_config = config.get("tts", {}).get("mimic3", {})
        lang = config.get("lang", "en-us")
        tts = Mimic3(lang, tts_config)
        tts.validator.validate()
        tts.init(bus)
        mimic_fallback_obj = tts

    return mimic_fallback_obj


def mimic_fallback_tts(utterance, ident, listen):
    """Speak utterance using fallback TTS if connection is lost.

    Args:
        utterance (str): sentence to speak
        ident (str): interaction id for metrics
        listen (bool): True if interaction should end with system listening
    """
    LOG.debug("Defaulting to Mimic3 as fallback for speech")
    tts = _get_mimic_fallback()
    tts.execute(utterance, ident, listen)


def handle_stop(event):
    """Handle stop message.

    Shutdown any speech.
    """
    global _last_stop_signal

    if check_for_signal("isSpeaking", -1):
        # while system_is_speaking():
        LOG.info("system still speaking, handling stop")
        # sent to llm to handle interruption by ending llm streaming thread
        # bus.emit(Message("llm.speech.interruption"))
        # tts.playback.set_interrupted_utterance(interrupted_utterance)
        tts.playback.clear()  # Clear here to get instant stop
        # time.sleep(1)

        _last_stop_signal = time.time()
        # bus.emit(Message("core.mic.stop_listen", {}))
        # bus.emit(
        #     Message("core.interrupted_utterance", {"utterance": interrupted_utterance})
        # )
        # LOG.info("Utterance interrupted")
        bus.emit(Message("core.stop.handled", {"by": "TTS"}))


def handle_interrupted_utterance(event):
    """Clear interrupted utterance from TTS object"""
    tts.playback.set_interrupted_utterance(None)


def init(messagebus):
    """Start speech related handlers.

    Args:
        messagebus: Connection to the messagebus
    """

    global bus
    global tts
    global llm
    global tts_hash
    global config
    # global interrupted_utterance

    bus = messagebus
    Configuration.set_config_update_handlers(bus)
    config = Configuration.get()
    bus.on("core.stop", handle_stop)
    bus.on("core.audio.speech.stop", handle_stop)
    bus.on("speak", handle_speak)
    bus.on("core.handled.interrupted_utterance", handle_interrupted_utterance)

    tts = TTSFactory.create()
    tts.init(bus)
    tts_hash = hash(str(config.get("tts", "")))


def shutdown():
    """Shutdown the audio service cleanly.

    Stop any playing audio and make sure threads are joined correctly.
    """
    if tts:
        tts.playback.stop()
        tts.playback.join()
    if mimic_fallback_obj:
        mimic_fallback_obj.playback.stop()
        mimic_fallback_obj.playback.join()
