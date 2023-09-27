"""Daemon launched at startup to handle skill activities.

In this repo, you will not find an entry called mycroft-skills in the bin
directory.  The executable gets added to the bin directory when installed
(see setup.py)
I'd say this is the main unit/central processing of this system
"""
from lingua_franca import load_languages

import core.lock
from core import dialog
from core.api import DeviceApi, is_paired, BackendDown

# from backend_client.pairing import is_paired
# from backend_client.exceptions import BackendDown
from core.audio import wait_while_speaking
from core.configuration import Configuration
from core.messagebus.message import Message
from core.util import (
    reset_sigint_handler,
    start_message_bus_client,
    wait_for_exit_signal,
)
from core.intent_services import IntentService
from core.util.log import LOG

# from core.util.process_utils import ProcessStatus, StatusCallbackMap

from core.skills.api import SkillApi
from core.skills.fallback_skill import FallbackSkill
from core.skills.event_scheduler import EventScheduler
from core.skills.skill_manager import (
    SkillManager,
    on_alive,
    on_ready,
    on_error,
    on_started,
    on_stopping,
)

RASPBERRY_PI_PLATFORMS = "picroft"


class DevicePrimer(object):
    """Container handling the device preparation.

    Args:
        message_bus_client: Bus client used to interact with the system
        config (dict): Core configuration
    """

    def __init__(self, message_bus_client, config):
        self.bus = message_bus_client
        self.platform = config["enclosure"].get("platform", "unknown")
        # self.enclosure = EnclosureAPI(self.bus)
        self.is_paired = False
        self.backend_down = False
        # Remember "now" at startup.  Used to detect clock changes.

    def prepare_device(self):
        """Internet dependent updates of various aspects of the device."""
        # self._get_pairing_status()
        self._update_system_clock()
        # self._update_system()
        # Above will block during update process and kill this instance if
        # new software is installed

        if self.backend_down:
            self._notify_backend_down()
        else:
            self.bus.emit(Message("core.internet.connected"))
            # self._ensure_device_is_paired()
            # self._update_device_attributes_on_backend()

    def _get_pairing_status(self):
        """Set an instance attribute indicating the device's pairing status"""
        try:
            self.is_paired = is_paired(ignore_errors=False)
        except BackendDown:
            LOG.error("Cannot complete device updates due to backend issues.")
            self.backend_down = True

        if self.is_paired:
            LOG.info("Device is paired")

    def _update_system_clock(self):
        """Force a sync of the local clock with the Network Time Protocol.

        The NTP sync is only forced on Raspberry Pi based devices.  The
        assumption being that these devices are only running Mycroft services.
        We don't want to sync the time on a Linux desktop device, for example,
        because it could have a negative impact on other software running on
        that device.
        """
        if self.platform in RASPBERRY_PI_PLATFORMS:
            LOG.info("Updating the system clock via NTP...")
            if self.is_paired:
                pass
                # Only display time sync message when paired because the prompt
                # to go to home.mycroft.ai will be displayed by the pairing
                # skill when pairing
                # self.enclosure.mouth_text(dialog.get("message_synching.clock"))
            self.bus.wait_for_response(
                Message("system.ntp.sync"), "system.ntp.sync.complete", 15
            )

    def _notify_backend_down(self):
        """Notify user of inability to communicate with the backend."""
        self._speak_dialog(dialog_id="backend.down")
        self.bus.emit(Message("backend.down"))

    def _ensure_device_is_paired(self):
        """Determine if device is paired, if not automatically start pairing.

        Pairing cannot be performed if there is no connection to the back end.
        So skip pairing if the backend is down.
        """
        if not self.is_paired and not self.backend_down:
            LOG.info("Device not paired, invoking the pairing skill")
            payload = dict(utterances=["pair my device"], lang="en-us")
            self.bus.emit(Message("recognizer_loop:utterance", payload))

    def _update_device_attributes_on_backend(self):
        """Communicate version information to the backend.

        The backend tracks core version, enclosure version, platform build
        and platform name for each device, if it is known.
        """
        if self.is_paired:
            LOG.info("Sending updated device attributes to the backend...")
            try:
                api = DeviceApi()
                api.update_version()
            except Exception:
                self._notify_backend_down()

    def _update_system(self):
        """Emit an update event that will be handled by the admin service."""
        if not self.is_paired:
            LOG.info("Attempting system update...")
            self.bus.emit(Message("system.update"))
            msg = Message(
                "system.update", dict(paired=self.is_paired, platform=self.platform)
            )
            resp = self.bus.wait_for_response(msg, "system.update.processing")

            if resp and (resp.data or {}).get("processing", True):
                self.bus.wait_for_response(
                    Message("system.update.waiting"), "system.update.complete", 1000
                )

    def _speak_dialog(self, dialog_id, wait=False):
        data = {"utterance": dialog.get(dialog_id)}
        self.bus.emit(Message("speak", data))
        if wait:
            wait_while_speaking()


def main(
    alive_hook=on_alive,
    started_hook=on_started,
    ready_hook=on_ready,
    error_hook=on_error,
    stopping_hook=on_stopping,
    watchdog=None,
):
    reset_sigint_handler()
    # Create PID file, prevent multiple instances of this service
    core.lock.Lock("skills")
    config = Configuration.get()
    lang_code = config.get("lang", "en-us")
    load_languages([lang_code, "en-us"])

    # Connect this process to the Core message bus
    bus = start_message_bus_client("SKILLS")
    _register_intent_services(bus)
    event_scheduler = EventScheduler(bus)
    SkillApi.connect_bus(bus)
    # skill_manager = _initialize_skill_manager(bus, watchdog)

    # This helps ensure that the events is logged specifically for the skill manager
    skill_manager = SkillManager(
        bus,
        watchdog,
        alive_hook=alive_hook,
        started_hook=started_hook,
        stopping_hook=stopping_hook,
        ready_hook=ready_hook,
        error_hook=error_hook,
    )

    skill_manager.start()
    device_primer = DevicePrimer(bus, config)
    device_primer.prepare_device()

    wait_for_exit_signal()
    shutdown(skill_manager, event_scheduler)


def _register_intent_services(bus):
    """Start up the all intent services and connect them as needed.

    Args:
        bus: messagebus client to register the services on
    """
    service = IntentService(bus)
    # Register handler to trigger fallback system
    bus.on("core.skills.fallback", FallbackSkill.make_intent_failure_handler(bus))
    return service


def shutdown(skill_manager, event_scheduler):
    LOG.info("Shutting down Skills service")
    if event_scheduler is not None:
        event_scheduler.shutdown()
    # Terminate all running threads that update skills
    if skill_manager is not None:
        skill_manager.stop()
        skill_manager.join()
    LOG.info("Skills service shutdown complete!")


if __name__ == "__main__":
    main()
