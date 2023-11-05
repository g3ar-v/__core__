# NOTE: Most consumers and producers registered handle messages for the voice system
# only
from threading import Lock

from core import dialog
from core.client.voice.listener import RecognizerLoop
from core.configuration import Configuration
from core.identity import IdentityManager
from core.lock import Lock as PIDLock  # Create/Support PID locking file
from core.messagebus.message import Message
from core.util import (
    create_daemon,
    reset_sigint_handler,
    start_message_bus_client,
    wait_for_exit_signal,
)
from core.util.log import LOG
from core.util.process_utils import ProcessStatus, StatusCallbackMap

bus = None  # messagebus connection
lock = Lock()
loop = None
config = None


def handle_record_begin():
    """Forward internal bus message to external bus."""
    LOG.info("Begin Recording...")
    context = {"client_name": "core_listener", "source": "audio"}
    # Forward message to stop any existing speech synthesis
    # NOTE: is the right place to handle stoping speech
    # bus.emit(Message("core.wakeword", context=context))
    bus.emit(Message("recognizer_loop:record_begin", context=context))


def handle_record_end():
    """Forward internal bus message to external bus."""
    LOG.info("End Recording...")
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("recognizer_loop:record_end", context=context))


def handle_no_internet():
    LOG.debug("Notifying enclosure of no internet connection")
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("enclosure.notify.no_internet", context=context))


def handle_awoken():
    """Forward core.awoken to the messagebus."""
    LOG.info("Listener is now Awake: ")
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("core.awoken", context=context))


def handle_wakeword():
    LOG.info("Wakeword Detected")
    # TODO: find a way to pause instead of stop
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("core.wakeword", context=context))
    # bus.emit(Message("recognizer_loop:wakeword", context=context))


def handle_utterance(event):
    LOG.info("Utterance: " + str(event["utterances"]))
    context = {
        "client_name": "core_listener",
        "source": "audio",
        "destination": ["skills"],
    }
    if "ident" in event:
        ident = event.pop("ident")
        context["ident"] = ident
    bus.emit(Message("recognizer_loop:utterance", event, context))


def handle_unknown():
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("core.speech.recognition.unknown", context=context))


def handle_speak(event):
    """
    Forward speak message to message bus.
    """
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("speak", event, context))


def handle_complete_intent_failure(event):
    """Extreme backup for answering completely unhandled intent requests."""
    LOG.info("Failed to find intent.")
    data = {"utterance": dialog.get("cant.intent")}
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("speak", data, context))


def handle_sleep(event):
    """Put the recognizer loop to sleep."""
    loop.sleep()


def handle_wake_up(event):
    """Wake up the the recognize loop."""
    loop.awaken()


def handle_mic_mute(event):
    """Mute the listener system."""
    loop.mute()


def handle_mic_unmute(event):
    """Unmute the listener system."""
    loop.unmute()


def handle_info_taking_too_long(event):
    """Core is taking too long to process information"""
    LOG.info("Info taking too long")
    data = {"utterance": dialog.get("taking_too_long")}
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("speak", data, context))


def handle_mic_listen(_):
    """Handler for core.mic.listen.

    Starts listening as if wakeword was spoken.
    """
    loop.responsive_recognizer.trigger_listen()


def handle_stop_listen(_):
    loop.reload()


def handle_mic_get_status(event):
    """Query microphone mute status."""
    data = {"muted": loop.is_muted()}
    bus.emit(event.response(data))


def handle_paired(event):
    """Update identity information with pairing data.

    This is done here to make sure it's only done in a single place.
    TODO: Is there a reason this isn't done directly in the pairing skill?
    """
    IdentityManager.update(event.data)


def handle_audio_start(event):
    """Mute recognizer loop."""
    if config.get("listener").get("mute_during_output"):
        loop.mute()


def handle_audio_end(event):
    """Request unmute, if more sources have requested the mic to be muted
    it will remain muted.
    """
    if config.get("listener").get("mute_during_output"):
        loop.unmute()  # restore


def handle_stop(event):
    """Handler for core.stop, i.e. button press."""
    loop.force_unmute()


def handle_open():
    """Reset UI to indicate ready for speech processing"""
    # EnclosureAPI(bus).reset
    pass


def on_ready():
    data = {"utterance": dialog.get("voice.available")}
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("speak", data, context))
    LOG.info("Speech client is ready.")


def on_stopping():
    data = {"utterance": dialog.get("voice.shutting")}
    context = {"client_name": "core_listener", "source": "audio"}
    bus.emit(Message("speak", data, context))
    LOG.info("Speech service is shutting down...")


def on_error(e="Unknown"):
    LOG.error("Audio service failed to launch ({}).".format(repr(e)))


def connect_loop_events(loop):
    loop.on("recognizer_loop:utterance", handle_utterance)
    loop.on("recognizer_loop:speech.recognition.unknown", handle_unknown)
    loop.on("speak", handle_speak)
    loop.on("core.wakeword", handle_wakeword)
    loop.on("recognizer_loop:record_begin", handle_record_begin)
    loop.on("recognizer_loop:awoken", handle_awoken)
    loop.on("recognizer_loop:wakeword", handle_wakeword)
    loop.on("recognizer_loop:record_end", handle_record_end)
    loop.on("recognizer_loop:no_internet", handle_no_internet)


def connect_bus_events(bus):
    # Register handlers for events on main messagebus
    # bus.on("open", handle_open)
    bus.on("complete_intent_failure", handle_complete_intent_failure)
    bus.on("recognizer_loop:sleep", handle_sleep)
    bus.on("recognizer_loop:wake_up", handle_wake_up)
    bus.on("core.mic.mute", handle_mic_mute)
    bus.on("core.mic.unmute", handle_mic_unmute)
    bus.on("core.mic.get_status", handle_mic_get_status)
    bus.on("core.mic.listen", handle_mic_listen)
    bus.on("core.mic.stop_listen", handle_stop_listen)
    # bus.on("core.wakeword", handle_wakeword)
    bus.on("core.paired", handle_paired)
    bus.on("recognizer_loop:audio_output_start", handle_audio_start)
    bus.on("recognizer_loop:audio_output_timeout", handle_info_taking_too_long)
    bus.on("recognizer_loop:audio_output_end", handle_audio_end)


def main(
    ready_hook=on_ready,
    error_hook=on_error,
    stopping_hook=on_stopping,
    watchdog=lambda: None,
):
    global bus
    global loop
    global config
    try:
        reset_sigint_handler()
        PIDLock("voice")
        config = Configuration.get()
        bus = start_message_bus_client("VOICE")
        connect_bus_events(bus)
        callbacks = StatusCallbackMap(
            on_ready=ready_hook, on_error=error_hook, on_stopping=stopping_hook
        )
        status = ProcessStatus("speech", bus, callbacks)

        # Register handlers on internal RecognizerLoop bus
        loop = RecognizerLoop(watchdog)
        connect_loop_events(loop)
        create_daemon(loop.run)
        status.set_started()

    except Exception as e:
        error_hook(e)
    else:
        status.set_ready()
        wait_for_exit_signal()
        status.set_stopping()


if __name__ == "__main__":
    main()
