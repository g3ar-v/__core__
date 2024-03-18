import time
from threading import Lock

from core.configuration import Configuration
from core.messagebus.message import Message
from core.tts import TTSFactory
from core.tts.mimic3_tts import Mimic3
from core.util import check_for_signal, create_signal
from core.util.log import LOG
from core.util.metrics import Stopwatch

bus = None  # Messagebus connection
audio_config = None
tts = None
tts_hash = None
lock = Lock()
mimic_fallback_obj = None

_last_stop_signal = 0
interrupted_utterance = None


def handle_speak(event):
    """Processes "speak" messages by parsing sentences and invoking the TTS service."""
    global _last_stop_signal, interrupted_utterance, audio_config
    audio_config = Configuration.get().get("audio")
    Configuration.set_config_update_handlers(bus)

    # Ignore if the message is targeted but not to audio
    event.context = event.context or {}
    if event.context.get("destination") and not (
        "debug_cli" in event.context["destination"]
        or "audio" in event.context["destination"]
    ):
        return

    ident = event.context.get("ident", "unknown")

    with lock:
        utterance = event.data["utterance"]
        listen = event.data.get("expect_response", False)

        LOG.info(f"Speaking utterance: {utterance}")
        interrupted_utterance = utterance
        speak(utterance, ident, listen, audio_config)



def speak(utterance, ident, listen=False, audio_config=None):
    """Speaks the utterance using the selected TTS backend."""
    global tts, tts_hash, mimic_fallback_obj
    new_hash = hash(str(audio_config.get("tts", "")))
    LOG.debug(f"New hash of tts: {new_hash}")
    if tts_hash != new_hash:
        LOG.info("TTS configuration changed, re-initializing TTS")
        if tts:
            tts.playback.detach_tts(tts)
        tts = TTSFactory.create()
        tts.init(bus)
        tts_hash = new_hash

    try:
        if audio_config.get("audio", {}).get("stream_tts", {}) and tts.tts_name == "ElevenLabsTTS":
            LOG.info("Streaming Audio")
            create_signal("isSpeaking")
            tts.begin_audio()
            tts.stream_tts(utterance)
            tts.end_audio(listen)
            check_for_signal("isSpeaking")
        else:
            tts.execute(utterance, ident, listen)
    except Exception as e:
        mimic_fallback_tts(utterance, ident, listen)
        LOG.error(e)


def mimic_fallback_tts(utterance, ident, listen):
    """Uses Mimic3 as a fallback TTS when the primary TTS fails."""
    LOG.info("Defaulting to Mimic3 as fallback for speech")
    tts = _get_mimic_fallback()
    tts.execute(utterance, ident, listen)


def _get_mimic_fallback():
    """Initializes the fallback TTS (Mimic3) if necessary."""
    global mimic_fallback_obj
    if not mimic_fallback_obj:
        config = Configuration.get().get("audio", {})
        tts_config = config.get("tts", {}).get("mimic3", {})
        lang = config.get("lang", "en-us")
        tts = Mimic3(lang, tts_config)
        tts.validator.validate()
        tts.init(bus)
        mimic_fallback_obj = tts

    return mimic_fallback_obj


def handle_stop(event):
    """Handles stop messages by terminating any ongoing speech."""
    global _last_stop_signal

    if check_for_signal("isSpeaking", -1):
        LOG.info("System still speaking, handling stop")
        tts.playback.clear()  # Instant stop
        _last_stop_signal = time.time()
        bus.emit(Message("core.stop.handled", {"by": "TTS"}))


def handle_interrupted_utterance(event):
    """Clears the interrupted utterance from the TTS object."""
    tts.playback.set_interrupted_utterance(None)


def init(messagebus):
    """Initializes speech-related handlers."""
    global bus, tts, tts_hash, audio_config

    bus = messagebus
    Configuration.set_config_update_handlers(bus)
    audio_config = Configuration.get().get("audio")
    bus.on("core.stop", handle_stop)
    bus.on("core.audio.speech.stop", handle_stop)
    bus.on("speak", handle_speak)
    bus.on("core.handled.interrupted_utterance", handle_interrupted_utterance)

    tts = TTSFactory.create()
    tts.init(bus)
    tts_hash = hash(str(audio_config.get("tts", "")))
    LOG.debug(f"TTS initialized hash: {tts_hash}")


def shutdown():
    """Shuts down the audio service cleanly, stopping any playing audio."""
    if tts:
        tts.playback.stop()
        tts.playback.join()
    if mimic_fallback_obj:
        mimic_fallback_obj.playback.stop()
        mimic_fallback_obj.playback.join()
