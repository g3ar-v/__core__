import re
import time
from threading import Lock

from core.configuration import Configuration
from core.llm import LLM
from core.util.metrics import Stopwatch
from core.tts import TTSFactory
from core.util import check_for_signal
from core.util.log import LOG
from core.messagebus.message import Message

# from core.tts.remote_tts import RemoteTTSException
from core.tts.mimic3_tts import Mimic3

bus = None  # messagebus connection
config = None
tts = None
tts_hash = None
llm = LLM()
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

    start = time.time()  # Time of speech request
    with lock:
        stopwatch = Stopwatch()
        stopwatch.start()
        utterance = event.data["utterance"]
        listen = event.data.get("expect_response", False)
        # This is a bit of a hack for Picroft.  The analog audio on a Pi blocks
        # for 30 seconds fairly often, so we don't want to break on periods
        # (decreasing the chance of encountering the block).  But we will
        # keep the split for non-Picroft installs since it give user feedback
        # faster on longer phrases.
        # HACK: this works for now but should it be here and should all messages be
        # tracked?
        llm.message_history.add_ai_message(utterance)
        # NOTE: is there an efficient way of getting the previous utterance?
        tts.store_interrupted_utterance(utterance)
        # TODO: Remove or make an option?  This is really a hack, anyway,
        # so we likely will want to get rid of this when not running on Mimic
        if (
            config.get("enclosure", {}).get("platform") != "picroft"
            and len(re.findall("<[^>]*>", utterance)) == 0
        ):
            chunks = tts.preprocess_utterance(utterance)
            # Apply the listen flag to the last chunk, set the rest to False
            chunks = [
                (chunks[i], listen if i == len(chunks) - 1 else False)
                for i in range(len(chunks))
            ]
            for chunk, listen in chunks:
                # Check if somthing has aborted the speech
                if _last_stop_signal > start or check_for_signal("buttonPress"):
                    # Clear any newly queued speech
                    tts.playback.clear()
                    break
                try:
                    mute_and_speak(chunk, ident, listen)

                except KeyboardInterrupt:
                    raise
                except Exception:
                    LOG.error("Error in mute_and_speak", exc_info=True)
        else:
            mute_and_speak(utterance, ident, listen)

        stopwatch.stop()


def mute_and_speak(utterance, ident, listen=False):
    """Mute mic and start speaking the utterance using selected tts backend.

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

    LOG.info("Speak: " + utterance)
    try:
        tts.execute(utterance, ident, listen)
    # except RemoteTTSException as e:
    #     LOG.error(e)
    #     mimic_fallback_tts(utterance, ident, listen)
    except Exception:
        LOG.exception("TTS execution failed.")


# TODO: check mimic3 is the fallback and if it works
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
        listen (bool): True if interaction should end with mycroft listening
    """
    LOG.debug("Defaulting to Mimic3 as fallback for speech")
    tts = _get_mimic_fallback()
    tts.execute(utterance, ident, listen)


def handle_stop(event):
    """Handle stop message.

    Shutdown any speech.
    """
    global _last_stop_signal
    global interrupted_utterance

    if check_for_signal("isSpeaking", -1):
        _last_stop_signal = time.time()
        interrupted_utterance = tts.get_interrupted_utterance()
        LOG.info("Utterance interrupted")
        tts.playback.clear()  # Clear here to get instant stop
        bus.emit(Message("core.stop.handled", {"by": "TTS"}))
        bus.emit(
            Message("core.interrupted_utterance", {"utterance": interrupted_utterance})
        )


def handle_interrupted_utterance(event):
    """Clear interrupted utterance from TTS object"""
    tts.store_interrupted_utterance(None)


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
    global interrupted_utterance

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
