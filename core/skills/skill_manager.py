# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
""""Load, update and manage skills on this device."""
import os
import time
from inspect import signature
from glob import glob
from os.path import basename
from threading import Thread, Event, Lock
from time import sleep, monotonic

from ovos_backend_client.pairing import is_paired
from core.messagebus.client import MessageBusClient
from core import Message
from core.configuration import Configuration as SysConf
from ovos_config.config import Configuration
from ovos_config.locations import get_xdg_config_save_path
from ovos_plugin_manager.skills import find_skill_plugins
# from ovos_utils.enclosure.api import EnclosureAPI
from ovos_utils.file_utils import FileWatcher
from ovos_utils.gui import is_gui_connected
from core.util.log import LOG
from core.util.network_utils import is_connected

from .msm_wrapper import create_msm as msm_creator, build_msm_config
from ovos_utils.process_utils import ProcessStatus, StatusCallbackMap, ProcessState
from ovos_utils.skills.locations import get_skill_directories
# from ovos_workshop.skill_launcher import SKILL_MAIN_MODULE
from ovos_workshop.skill_launcher import PluginSkillLoader

from .skill_loader import SkillLoader
from .skill_updater import SkillUpdater
from .settings import SkillSettingsDownloader

SKILL_MAIN_MODULE = '__init__.py'


class UploadQueue:
    """Queue for holding loaders with data that still needs to be uploaded.

    This queue can be used during startup to capture all loaders
    and then processing can be triggered at a later stage when the system is
    connected to the backend.

    After all queued settingsmeta has been processed and the queue is empty
    the queue will set the self.started flag.
    """

    def __init__(self):
        self._queue = []
        self.started = False
        self.lock = Lock()

    def start(self):
        """Start processing of the queue."""
        self.started = True
        self.send()

    def stop(self):
        """Stop the queue, and hinder any further transmissions."""
        self.started = False

    def send(self):
        """Loop through all stored loaders triggering settingsmeta upload."""
        with self.lock:
            queue = self._queue
            self._queue = []
        if queue:
            LOG.info('New Settings meta to upload.')
            for loader in queue:
                if self.started:
                    loader.instance.settings_meta.upload()
                else:
                    break

    def __len__(self):
        return len(self._queue)

    def put(self, loader):
        """Append a skill loader to the queue.

        If a loader is already present it's removed in favor of the new entry.
        """
        if self.started:
            LOG.info('Updating settings meta during runtime...')
        with self.lock:
            # Remove existing loader
            self._queue = [e for e in self._queue if e != loader]
            self._queue.append(loader)


def _shutdown_skill(instance):
    """Shutdown a skill.

     Call the default_shutdown method of the skill, will produce a warning if
     the shutdown process takes longer than 1 second.

     Args:
         instance (SystemSkill): Skill instance to shutdown
    """
    try:
        ref_time = monotonic()
        # Perform the shutdown
        instance.default_shutdown()

        shutdown_time = monotonic() - ref_time
        if shutdown_time > 1:
            LOG.warning(f'{instance.skill_id} shutdown took {shutdown_time} seconds')
    except Exception:
        LOG.exception(f'Failed to shut down skill: {instance.skill_id}')


def on_started():
    LOG.info('Skills Manager is starting up.')


def on_alive():
    LOG.info('Skills Manager is alive.')


def on_ready():
    LOG.info('Skills Manager is ready.')


def on_error(e='Unknown'):
    LOG.info(f'Skills Manager failed to launch ({e})')


def on_stopping():
    LOG.info('Skills Manager is shutting down...')


class SkillManager(Thread):

    _msm = None

    def __init__(self, bus, watchdog=None, alive_hook=on_alive, started_hook=on_started,
                 ready_hook=on_ready, error_hook=on_error, stopping_hook=on_stopping):
        """Constructor

        Args:
            bus (event emitter): messagebus connection
            watchdog (callable): optional watchdog function
        """
        super(SkillManager, self).__init__()
        self.bus = bus
        self._settings_watchdog = None
        # Set watchdog to argument or function returning None
        self._watchdog = watchdog or (lambda: None)
        callbacks = StatusCallbackMap(on_started=started_hook,
                                      on_alive=alive_hook,
                                      on_ready=ready_hook,
                                      on_error=error_hook,
                                      on_stopping=stopping_hook)
        self.status = ProcessStatus('skills', callback_map=callbacks)
        self.status.set_started()

        self._lock = Lock()
        self._setup_event = Event()
        self._stop_event = Event()
        self._connected_event = Event()
        self._internet_loaded = Event()
        self._allow_state_reloads = True
        self.upload_queue = UploadQueue()
        self.skill_updater = SkillUpdater()

        self.config = Configuration()
        self.sysconf = SysConf.get()

        self.skill_loaders = {}
        self.plugin_skills = {}
        # self.enclosure = EnclosureAPI(bus)
        self.initial_load_complete = False
        self.num_install_retries = 0
        self.empty_skill_dirs = set()  # Save a record of empty skill dirs.
        self.settings_downloader = SkillSettingsDownloader(self.bus)

        self._define_message_bus_events()
        self.daemon = True

        self.status.bind(self.bus)
        self._init_filewatcher()

    def _init_filewatcher(self):
        # monitor skill settings files for changes
        sspath = f"{get_xdg_config_save_path('core')}/skills/"
        os.makedirs(sspath, exist_ok=True)
        self._settings_watchdog = FileWatcher([sspath],
                                              callback=self._handle_settings_file_change,
                                              recursive=True,
                                              ignore_creation=True)

    def _handle_settings_file_change(self, path: str):
        if path.endswith("/settings.json"):
            skill_id = path.split("/")[-2]
            LOG.info(f"skill settings.json change detected for {skill_id}")
            self.bus.emit(Message("core.skills.settings_changed",
                                  {"skill_id": skill_id}))

    def _sync_skill_loading_state(self):
        resp = self.bus.wait_for_response(Message("ovos.PHAL.internet_check"))
        network = False
        internet = False

        if resp:
            if resp.data.get('internet_connected'):
                network = internet = True
            elif resp.data.get('network_connected'):
                network = True
        else:
            LOG.debug("ovos-phal-plugin-connectivity-events not detected, performing direct network checks")
            network = internet = is_connected()

        if internet and not self._connected_event.is_set():
            LOG.debug("notify internet connected")
            self.bus.emit(Message("core.internet.connected"))
        

    def _define_message_bus_events(self):
        """Define message bus events with handlers defined in this class."""
        # Update upon request
        self.bus.on('skill.converse.request', self.handle_converse_request)
        self.bus.on('skillmanager.list', self.send_skill_list)
        self.bus.on('skillmanager.deactivate', self.deactivate_skill)
        self.bus.on('skillmanager.keep', self.deactivate_except)
        self.bus.on('skillmanager.activate', self.activate_skill)
        self.bus.on('core.skills.initialized',
                      self.handle_check_device_readiness)
        self.bus.on('core.skills.trained', self.handle_initial_training)

        # load skills waiting for connectivity
        self.bus.on("core.internet.connected", self.handle_internet_connected)
        self.bus.on("core.internet.disconnected", self.handle_internet_disconnected)
        self.bus.on("core.skills.settings.update", self.settings_downloader.download)

    def is_device_ready(self):
        is_ready = False
        # different setups will have different needs
        # eg, a server does not care about audio
        # pairing -> device is paired
        # internet -> device is connected to the internet - NOT IMPLEMENTED
        # skills -> skills reported ready
        # speech -> stt reported ready
        # audio -> audio playback reported ready
        # gui -> gui websocket reported ready - NOT IMPLEMENTED
        # enclosure -> enclosure/HAL reported ready - NOT IMPLEMENTED
        services = {k: False for k in
                    self.sysconf.get("ready_settings", ["skills"])}
        start = monotonic()
        while not is_ready:
            # is_ready = self.check_services_ready(services)
            if is_ready:
                break
            elif monotonic() - start >= 60:
                raise TimeoutError(
                    f'Timeout waiting for services start. services={services}')
            else:
                sleep(3)
        return is_ready

    def handle_check_device_readiness(self, message):
        ready = False
        while not ready:
            try:
                ready = self.is_device_ready()
            except TimeoutError:
                if is_paired():
                    LOG.warning("System should already have reported ready!")
                sleep(5)

        LOG.info("System is all loaded and ready to roll!")
        self.bus.emit(message.reply('core.ready'))

    # There might be an error from here on what config file is being accessed
    # check it out later and clean
    @property
    def skills_config(self):
        return self.sysconf['skills']

    @property
    def msm(self):
        if self._msm is None:
            msm_config = build_msm_config(self.sysconf)
            self._msm = msm_creator(msm_config)

        return self._msm

    @staticmethod
    def create_msm():
        LOG.debug('instantiating msm via static method...')
        msm_config = build_msm_config(SysConf.get())
        msm_instance = msm_creator(msm_config)

        return msm_instance

    def schedule_now(self, _):
        self.skill_updater.next_download = time() - 1

    def _start_settings_update(self):
        LOG.info('Start settings update')
        self.skill_updater.post_manifest(reload_skills_manifest=True)
        self.upload_queue.start()
        LOG.info('All settings meta has been processed or upload has started')
        self.settings_downloader.download()
        LOG.info('Skill settings downloading has started')

    def handle_paired(self, _):
        """Trigger upload of skills manifest after pairing."""
        self._start_settings_update()

    def handle_internet_disconnected(self, message):
        if self._allow_state_reloads:
            self._connected_event.clear()
            self._unload_on_internet_disconnect()

    def handle_internet_connected(self, message):
        if not self._connected_event.is_set():
            LOG.debug("Internet Connected")
            # self._network_event.set()
            self._connected_event.set()

    def load_plugin_skills(self, network=None, internet=None):
        if network is None:
            network = self._network_event.is_set()
        if internet is None:
            internet = self._connected_event.is_set()
        plugins = find_skill_plugins()
        loaded_skill_ids = [basename(p) for p in self.skill_loaders]
        for skill_id, plug in plugins.items():
            if skill_id not in self.plugin_skills and skill_id not in loaded_skill_ids:
                skill_loader = self._get_plugin_skill_loader(skill_id, init_bus=False)
                requirements = skill_loader.runtime_requirements
                if not network and requirements.network_before_load:
                    continue
                if not internet and requirements.internet_before_load:
                    continue
                self._load_plugin_skill(skill_id, plug)

    def _get_internal_skill_bus(self):
        if not self.config["websocket"].get("shared_connection", True):
            # see BusBricker skill to understand why this matters
            # any skill can manipulate the bus from other skills
            # this patch ensures each skill gets it's own
            # connection that can't be manipulated by others
            # https://github.com/EvilJarbas/BusBrickerSkill
            bus = MessageBusClient(cache=True)
            bus.run_in_thread()
        else:
            bus = self.bus
        return bus

    def _get_plugin_skill_loader(self, skill_id, init_bus=True):
        bus = None
        if init_bus:
            bus = self._get_internal_skill_bus()
        return PluginSkillLoader(bus, skill_id)

    def _load_plugin_skill(self, skill_id, skill_plugin):
        skill_loader = self._get_plugin_skill_loader(skill_id)
        try:
            load_status = skill_loader.load(skill_plugin)
        except Exception:
            LOG.exception(f'Load of skill {skill_id} failed!')
            load_status = False
        finally:
            self.plugin_skills[skill_id] = skill_loader

        return skill_loader if load_status else None

    def load_priority(self):
        skills = {skill.name: skill for skill in self.msm.all_skills}
        priority_skills = self.skills_config.get("priority_skills", [])
        for skill_name in priority_skills:
            skill = skills.get(skill_name)
            if skill is not None:
                if not skill.is_local:
                    try:
                        self.msm.install(skill)
                    except Exception:
                        log_msg = 'Downloading priority skill: {} failed'
                        LOG.exception(log_msg.format(skill_name))
                        continue
                loader = self._load_skill(skill.path)
                if loader:
                    self.upload_queue.put(loader)
            else:
                LOG.error(
                    'Priority skill {} can\'t be found'.format(skill_name)
                )

        self._alive_status = True

    def handle_initial_training(self, message):
        self.initial_load_complete = True

    def run(self):
        """Load skills and update periodically from disk and internet."""
        self._remove_git_locks()

        self.load_priority()

        self.status.set_alive()

        self._load_on_startup()

        if self.skills_config.get("wait_for_internet", False):
            LOG.warning("`wait_for_internet` is a deprecated option, update to "
                        "specify `network_skills`or `internet_skills` in "
                        "`ready_settings`")
            # NOTE - self._connected_event will never be set
            # if PHAL plugin is not running to emit the connected events
            while not self._connected_event.is_set():
                # ensure we dont block here forever if plugin not installed
                self._sync_skill_loading_state()
                sleep(1)
            LOG.debug("Internet Connected")
        else:
            # trigger a sync so we dont need to wait for the plugin to volunteer info
            self._sync_skill_loading_state()

        if "internet_skills" in self.config.get("ready_settings"):
            self._connected_event.wait()  # Wait for user to connect to network
            if self._internet_loaded.wait(self._network_skill_timeout):
                LOG.debug("Internet skills loaded")
            else:
                LOG.error("Gave up waiting for internet skills to load")
        if not self._internet_loaded.is_set():
            self.bus.emit(Message(
                'core.skills.error',
                {'internet_loaded': self._internet_loaded.is_set()}))
        self.bus.emit(Message('core.skills.initialized'))

        # wait for initial intents training
        LOG.debug("Waiting for initial training")
        while not self.initial_load_complete:
            sleep(0.5)
        self.status.set_ready()

        if not self._connected_event.is_set():
            LOG.info("Offline Skills loaded, waiting for Internet to load more!")

        # Scan the file folder that contains Skills.  If a Skill is updated,
        # unload the existing version from memory and reload from the disk.
        while not self._stop_event.is_set():
            try:
                self._unload_removed_skills()
                self._reload_modified_skills()
                self._load_new_skills()
                self._watchdog()
                sleep(2)  # Pause briefly before beginning next scan
            except Exception:
                LOG.exception('Something really unexpected has occurred '
                              'and the skill manager loop safety harness was '
                              'hit.')
                sleep(30)

    def _remove_git_locks(self):
        """If git gets killed from an abrupt shutdown it leaves lock files."""
        lock_path = os.path.join(self.msm.skills_dir, '*/.git/index.lock')
        for i in glob(lock_path):
            LOG.warning('Found and removed git lock file: ' + i)
            os.remove(i)

    def _load_on_internet(self):
        LOG.info('Loading skills that require internet (and network)...')
        # self._load_new_skills(network=True, internet=True)
        self._load_new_skills()
        self._internet_loaded.set()
        self._network_loaded.set()

    def _unload_on_network_disconnect(self):
        """ unload skills that require network to work """
        with self._lock:
            for skill_dir in self._get_skill_directories():
                # by definition skill_id == folder name
                skill_id = os.path.basename(skill_dir)
                skill_loader = self._get_skill_loader(skill_dir, init_bus=False)
                requirements = skill_loader.runtime_requirements
                if requirements.requires_network and \
                        not requirements.no_network_fallback:
                    # unload until network is back
                    self._unload_skill(skill_dir)

    def _unload_on_internet_disconnect(self):
        """ unload skills that require internet to work """
        with self._lock:
            for skill_dir in self._get_skill_directories():
                # by definition skill_id == folder name
                skill_id = os.path.basename(skill_dir)
                skill_loader = self._get_skill_loader(skill_dir, init_bus=False)
                requirements = skill_loader.runtime_requirements
                if requirements.requires_internet and \
                        not requirements.no_internet_fallback:
                    # unload until internet is back
                    self._unload_skill(skill_dir)

    def _unload_on_gui_disconnect(self):
        """ unload skills that require gui to work """
        with self._lock:
            for skill_dir in self._get_skill_directories():
                # by definition skill_id == folder name
                skill_id = os.path.basename(skill_dir)
                skill_loader = self._get_skill_loader(skill_dir, init_bus=False)
                requirements = skill_loader.runtime_requirements
                if requirements.requires_gui and \
                        not requirements.no_gui_fallback:
                    # unload until gui is back
                    self._unload_skill(skill_dir)

    def _load_on_startup(self):
        """Handle initial skill load."""
        LOG.info('Loading offline skills...')
        self.bus.emit(Message('core.skills.initialized'))
        self._load_new_skills()

    def _reload_modified_skills(self):
        """Handle reload of recently changed skill(s)"""
        for skill_dir in self._get_skill_directories():
            try:
                skill_loader = self.skill_loaders.get(skill_dir)
                if skill_loader is not None and skill_loader.reload_needed():
                    # If reload succeed add settingsmeta to upload queue
                    if skill_loader.reload():
                        self.upload_queue.put(skill_loader)
            except Exception:
                LOG.exception('Unhandled exception occured while '
                              'reloading {}'.format(skill_dir))

    def _load_new_skills(self):
        """Handle load of skills installed since startup."""
        for skill_dir in self._get_skill_directories():
            if skill_dir not in self.skill_loaders:
                loader = self._load_skill(skill_dir)
                if loader:
                    self.upload_queue.put(loader)

    def _get_skill_loader(self, skill_directory, init_bus=True):
        bus = None
        if init_bus:
            bus = self._get_internal_skill_bus()
        return SkillLoader(bus, skill_directory)

    def _load_skill(self, skill_directory):
        skill_loader = self._get_skill_loader(skill_directory)
        try:
            load_status = skill_loader.load()
        except Exception:
            LOG.exception(f'Load of skill {skill_directory} failed!')
            load_status = False
        finally:
            self.skill_loaders[skill_directory] = skill_loader

        return skill_loader if load_status else None

    def _unload_skill(self, skill_dir):
        if skill_dir in self.skill_loaders:
            skill = self.skill_loaders[skill_dir]
            LOG.info(f'removing {skill.skill_id}')
            try:
                skill.unload()
            except Exception:
                LOG.exception('Failed to shutdown skill ' + skill.id)
            del self.skill_loaders[skill_dir]

    def _get_skill_directories(self):
        skill_glob = glob(os.path.join(self.msm.skills_dir, '*/'))

        skill_directories = []
        for skill_dir in skill_glob:
            # TODO: all python packages must have __init__.py!  Better way?
            # check if folder is a skill (must have __init__.py)
            if SKILL_MAIN_MODULE in os.listdir(skill_dir):
                skill_directories.append(skill_dir.rstrip('/'))
                if skill_dir in self.empty_skill_dirs:
                    self.empty_skill_dirs.discard(skill_dir)
            else:
                if skill_dir not in self.empty_skill_dirs:
                    self.empty_skill_dirs.add(skill_dir)
                    LOG.debug('Found skills directory with no skill: ' +
                              skill_dir)

        return skill_directories

    def _unload_removed_skills(self):
        """Shutdown removed skills."""
        skill_dirs = self._get_skill_directories()
        # Find loaded skills that don't exist on disk
        removed_skills = [
            s for s in self.skill_loaders.keys() if s not in skill_dirs
        ]
        for skill_dir in removed_skills:
            skill = self.skill_loaders[skill_dir]
            LOG.info('removing {}'.format(skill.skill_id))
            try:
                skill.unload()
            except Exception:
                LOG.exception('Failed to shutdown skill ' + skill.id)
            del self.skill_loaders[skill_dir]

        # If skills were removed make sure to update the manifest on the
        # core backend.
        if removed_skills:
            self.skill_updater.post_manifest(reload_skills_manifest=True)

    def _update_skills(self):
        """Update skills once an hour if update is enabled"""
        do_skill_update = (
            time() >= self.skill_updater.next_download and
            self.skills_config["auto_update"]
        )
        if do_skill_update:
            self.skill_updater.update_skills()

    def _unload_plugin_skill(self, skill_id):
        if skill_id in self.plugin_skills:
            LOG.info('Unloading plugin skill: ' + skill_id)
            skill_loader = self.plugin_skills[skill_id]
            if skill_loader.instance is not None:
                try:
                    skill_loader.instance.default_shutdown()
                except Exception:
                    LOG.exception('Failed to shutdown plugin skill: ' + skill_loader.skill_id)
            self.plugin_skills.pop(skill_id)

    def is_alive(self, message=None):
        """Respond to is_alive status request."""
        return self.status.state >= ProcessState.ALIVE

    def is_all_loaded(self, message=None):
        """ Respond to all_loaded status request."""
        return self.status.state == ProcessState.READY

    def send_skill_list(self, _):
        """Send list of loaded skills."""
        try:
            message_data = {}
            for skill_dir, skill_loader in self.skill_loaders.items():
                message_data[skill_loader.skill_id] = dict(
                    active=skill_loader.active and skill_loader.loaded,
                    id=skill_loader.skill_id
                )
            self.bus.emit(Message('core.skills.list', data=message_data))
        except Exception:
            LOG.exception('Failed to send skill list')

    def deactivate_skill(self, message):
        """Deactivate a skill."""
        try:
            # TODO handle external skills, OVOSAbstractApp/Hivemind skills are not accounted for
            skills = {**self.skill_loaders, **self.plugin_skills}
            for skill_loader in skills.values():
                if message.data['skill'] == skill_loader.skill_id:
                    LOG.info("Deactivating skill: " + skill_loader.skill_id)
                    skill_loader.deactivate()
        except Exception:
            LOG.exception('Failed to deactivate ' + message.data['skill'])

    def deactivate_except(self, message):
        """Deactivate all skills except the provided."""
        try:
            skill_to_keep = message.data['skill']
            LOG.info('Deactivating all skills except {}'.format(skill_to_keep))
            loaded_skill_file_names = [
                os.path.basename(skill_dir) for skill_dir in self.skill_loaders
            ]
            if skill_to_keep in loaded_skill_file_names:
                for skill in self.skill_loaders.values():
                    if skill.skill_id != skill_to_keep:
                        skill.deactivate()
            else:
                LOG.info('Couldn\'t find skill ' + message.data['skill'])
        except Exception:
            LOG.exception('An error occurred during skill deactivation!')

    def activate_skill(self, message):
        """Activate a deactivated skill."""
        try:
            for skill_loader in self.skill_loaders.values():
                if (message.data['skill'] in ('all', skill_loader.skill_id) and
                        not skill_loader.active):
                    skill_loader.activate()
        except Exception:
            LOG.exception('Couldn\'t activate skill')

    def stop(self):
        """Tell the manager to shutdown."""
        self.status.set_stopping()
        self._stop_event.set()

        # Do a clean shutdown of all skills
        for skill_loader in self.skill_loaders.values():
            if skill_loader.instance is not None:
                _shutdown_skill(skill_loader.instance)

        # Do a clean shutdown of all plugin skills
        for skill_id in list(self.plugin_skills.keys()):
            self._unload_plugin_skill(skill_id)

        if self._settings_watchdog:
            self._settings_watchdog.shutdown()

    def handle_converse_request(self, message):
        """Check if the targeted skill id can handle conversation

        If supported, the conversation is invoked.
        """
        skill_id = message.data['skill_id']

        # loop trough skills list and call converse for skill with skill_id
        skill_found = False
        for skill_loader in self.skill_loaders.values():
            if skill_loader.skill_id == skill_id:
                skill_found = True
                if not skill_loader.loaded:
                    error_message = 'converse requested but skill not loaded'
                    self._emit_converse_error(message, skill_id, error_message)
                    break
                try:
                    # check the signature of a converse method
                    # to either pass a message or not
                    if len(signature(
                            skill_loader.instance.converse).parameters) == 1:
                        result = skill_loader.instance.converse(
                            message=message)
                    else:
                        utterances = message.data['utterances']
                        lang = message.data['lang']
                        result = skill_loader.instance.converse(
                            utterances=utterances, lang=lang)
                    self._emit_converse_response(result, message, skill_loader)
                except Exception:
                    error_message = 'exception in converse method'
                    LOG.exception(error_message)
                    self._emit_converse_error(message, skill_id, error_message)
                finally:
                    break

        if not skill_found:
            error_message = 'skill id does not exist'
            self._emit_converse_error(message, skill_id, error_message)

    def _emit_converse_error(self, message, skill_id, error_msg):
        """Emit a message reporting the error back to the intent service."""
        reply = message.reply('skill.converse.response',
                              data=dict(skill_id=skill_id, error=error_msg))
        self.bus.emit(reply)

    def _emit_converse_response(self, result, message, skill_loader):
        reply = message.reply(
            'skill.converse.response',
            data=dict(skill_id=skill_loader.skill_id, result=result)
        )
        self.bus.emit(reply)
