"""Daemon launched at startup to handle skill activities.

In this repo, you will not find an entry called mycroft-skills in the bin
directory.  The executable gets added to the bin directory when installed
(see setup.py)
I'd say this is the main unit/central processing of this system
"""

import time

# from lingua_franca import load_languages

import source.lock
from source.audio import wait_while_speaking
from source.core.api import SkillApi
from source.core.event_scheduler import EventScheduler
from source.core.fallback_skill import FallbackSkill
from source.core.skill_manager import SkillManager
from source.dialog import dialog
from source.intent_services import IntentService
from source.llm import LLM
from source.messagebus.message import Message
from source.util import (
    connected_to_the_internet,
    reset_sigint_handler,
    start_message_bus_client,
    wait_for_exit_signal,
)
from source.util.log import LOG
from source.util.process_utils import ProcessStatus, StatusCallbackMap

bus = None


def on_started():
    LOG.info("CORE SERVICE IS STARTING UP.")


def on_alive():
    LOG.info("CORE SERVICE IS ALIVE.")


def on_ready():
    LOG.info("CORE SERVICE IS READY.")
    _speak_dialog(dialog_id="finished.booting")


def on_error(e="Unknown"):
    LOG.info(f"CORE SERVICE FAILED TO LAUNCH ({e})")


def on_stopping():
    LOG.info("CORE SERVICE IS SHUTTING DOWN...")
    _speak("CORE component is shutting down...")


def main(
    alive_hook=on_alive,
    started_hook=on_started,
    ready_hook=on_ready,
    error_hook=on_error,
    stopping_hook=on_stopping,
    watchdog=None,
):
    global bus
    reset_sigint_handler()
    # Create PID file, prevent multiple instances of this service
    source.lock.Lock("core")
    # config = Configuration.get()
    # lang_code = config.get("lang", "en-us")
    # load_languages([lang_code, "en-us"])

    # Connect this process to the Core message bus
    bus = start_message_bus_client("CORE")
    _register_intent_services(bus)
    event_scheduler = EventScheduler(bus)
    callbacks = StatusCallbackMap(
        on_started=started_hook,
        on_alive=alive_hook,
        on_ready=ready_hook,
        on_error=error_hook,
        on_stopping=stopping_hook,
    )
    status = ProcessStatus("core", bus, callback_map=callbacks)
    LLM.initialize(bus)

    SkillApi.connect_bus(bus)
    skill_manager = _initialize_skill_manager(bus, watchdog)

    # This helps ensure that the events is logged specifically for the skill manager

    status.set_started()
    if _check_for_internet_connection(timeout=15) is False:
        _speak_dialog("not_connected_to_the_internet")

    if skill_manager is None:
        skill_manager = _initialize_skill_manager(bus, watchdog)

    skill_manager.start()

    while not skill_manager.is_alive():
        time.sleep(0.1)
    status.set_alive()

    while not skill_manager.is_all_loaded():
        time.sleep(0.1)
    status.set_ready()

    # add event logs to cli
    # bus.emit(Message("core.debug.log", data={"bus": True}))

    wait_for_exit_signal()
    status.set_stopping()
    shutdown(skill_manager, event_scheduler)


def _register_intent_services(bus):
    """Start up the all intent services and connect them as needed.

    Args:
        bus: messagebus client to register the services on
    """
    service = IntentService(bus)
    # Register handler to trigger fallback system
    bus.on("source.core.fallback", FallbackSkill.make_intent_failure_handler(bus))
    return service


def _initialize_skill_manager(bus, watchdog):
    """Create a thread that monitors the loaded skills, looking for updates

    Returns:
        SkillManager instance or None if it couldn't be initialized
    """
    try:
        skill_manager = SkillManager(bus, watchdog)
        # skill_manager.load_priority()
    except Exception:
        # skill manager couldn't be created, wait for network connection and
        # retry
        skill_manager = None
        LOG.info(
            "MSM is uninitialized and requires network connection to fetch "
            "skill information\nWill retry after internet connection is "
            "established."
        )

    return skill_manager


def _check_for_internet_connection(timeout):
    counter = 0
    while not connected_to_the_internet() and counter < timeout:
        time.sleep(1)
        counter += 1
    if not connected_to_the_internet():
        LOG.info("SYSTEM IS IN OFFLINE MODE")
        return False
    else:
        LOG.info("SYSTEM IS IN ONLINE MODE")
        return True


def _speak(dialog, wait=False):
    data = {"utterance": dialog}
    bus.emit(Message("speak", data))
    if wait:
        wait_while_speaking()


def _speak_dialog(dialog_id, wait=False):
    data = {"utterance": dialog.get(dialog_id)}
    bus.emit(Message("speak", data))
    if wait:
        wait_while_speaking()


def shutdown(skill_manager, event_scheduler):

    if event_scheduler is not None:
        event_scheduler.shutdown()
    # Terminate all running threads that update skills
    if skill_manager is not None:
        skill_manager.stop()
        skill_manager.join()
    LOG.info("CORE service shutdown complete!")


if __name__ == "__main__":
    main()
