import json
import os
import re
from os.path import exists, isfile, join, dirname

import xdg.BaseDirectory

from core import dialog
from core.messagebus.message import Message
from core.util.combo_lock import ComboLock
from core.util.file_utils import get_temp_path
from core.util import camel_case_split
from core.util.json_helper import load_commented_json, merge_dict
from core.util.log import LOG

from .locations import (
    DEFAULT_CONFIG,
    SYSTEM_CONFIG,
    USER_CONFIG
)


def is_remote_list(values):
    """Check if list corresponds to a backend formatted collection of dicts
    """
    for v in values:
        if not isinstance(v, dict):
            return False
        if "@type" not in v.keys():
            return False
    return True


def translate_remote(config, setting):
    """Translate config names from server to equivalents for mycroft-core.

    Args:
        config:     base config to populate
        settings:   remote settings to be translated
    """
    IGNORED_SETTINGS = ["uuid", "@type", "active", "user", "device"]

    for k, v in setting.items():
        if k not in IGNORED_SETTINGS:
            # Translate the CamelCase values stored remotely into the
            # Python-style names used within mycroft-core.
            key = re.sub(r"Setting(s)?", "", k)
            key = camel_case_split(key).replace(" ", "_").lower()
            if isinstance(v, dict):
                config[key] = config.get(key, {})
                translate_remote(config[key], v)
            elif isinstance(v, list):
                if is_remote_list(v):
                    if key not in config:
                        config[key] = {}
                    translate_list(config[key], v)
                else:
                    config[key] = v
            else:
                config[key] = v


def translate_list(config, values):
    """Translate list formated by mycroft server.

    Args:
        config (dict): target config
        values (list): list from mycroft server config
    """
    for v in values:
        module = v["@type"]
        if v.get("active"):
            config["module"] = module
        config[module] = config.get(module, {})
        translate_remote(config[module], v)


class LocalConf(dict):
    """Config dictionary from file."""
    _lock = ComboLock(get_temp_path('local-conf.lock'))

    def __init__(self, path):
        super(LocalConf, self).__init__()
        self.is_valid = True  # is loaded json valid, updated when load occurs
        if path:
            self.path = path
            self.load_local(path)

    def load_local(self, path):
        """Load local json file into self.

        Args:
            path (str): file to load
        """
        if exists(path) and isfile(path):
            try:
                config = load_commented_json(path)
                for key in config:
                    self.__setitem__(key, config[key])

                LOG.debug("Configuration {} loaded".format(path))
            except Exception as e:
                LOG.error("Error loading configuration '{}'".format(path))
                LOG.error(repr(e))
                self.is_valid = False
        else:
            LOG.debug("Configuration '{}' not defined, skipping".format(path))

    def store(self, path=None, force=False):
        """Save config to disk.

        The cache will be used if the remote is unreachable to load settings
        that are as close to the user's as possible.

        path (str): path to store file to, if missing will use the path from
                    where the config was loaded.
        force (bool): Set to True if writing should occur despite the original
                      was malformed.

        Returns:
            (bool) True if save was successful, else False.
        """
        result = False
        with self._lock:
            path = path or self.path
            config_dir = dirname(path)
            if not exists(config_dir):
                os.makedirs(config_dir)

            if self.is_valid or force:
                with open(path, 'w') as f:
                    json.dump(self, f, indent=2)
                result = True
            else:
                LOG.warning((f'"{path}" was not a valid config file when '
                             'loaded, will not save config. Please correct '
                             'the json or remove it to allow updates.'))
                result = False
        return result

    def merge(self, conf):
        merge_dict(self, conf)


class RemoteConf(LocalConf):
    # _lock = ComboLock(get_temp_path('remote-conf.lock'))
    """Config dictionary fetched from local backend"""

    def __init__(self, cache=None):
        super(RemoteConf, self).__init__(None)

        cache = cache or join(xdg.BaseDirectory.xdg_cache_home, 'mycroft',
                              'web_cache.json')

    def reload(self):
        try:
            from core.api import is_paired
            from core.api import RemoteConfigManager

            if not is_paired():
                self.load_local(self.path)
                return

            remote = RemoteConfigManager()

            remote.download()
            for key in remote.config:
                self.__setitem__(key, remote.config[key])

            self.store(self.path)

        except Exception as e:
            LOG.error(f"Exception fetching remote configuration: {e}")
            self.load_local(self.path)


class Configuration:
    """Namespace for operations on the configuration singleton."""
    __config = {}  # Cached config
    __patch = {}  # Patch config that skills can update to override config

    @staticmethod
    def get(configs=None, cache=True, remote=True):
        """Get configuration

        Returns cached instance if available otherwise builds a new
        configuration dict.

        Args:
            configs (list): List of configuration dicts
            cache (boolean): True if the result should be cached
            remote (boolean): False if the Remote settings shouldn't be loaded

        Returns:
            (dict) configuration dictionary.
        """
        if Configuration.__config:
            return Configuration.__config
        else:
            return Configuration.load_config_stack(configs, cache, remote)

    @staticmethod
    def load_config_stack(configs=None, cache=False, remote=True):
        """Load a stack of config dicts into a single dict

        Args:
            configs (list): list of dicts to load
            cache (boolean): True if result should be cached
            remote (boolean): False if the Mycroft Home settings shouldn't
                              be loaded
        Returns:
            (dict) merged dict of all configuration files
        """
        if not configs:
            configs = []

            # First use the patched config
            configs.append(Configuration.__patch)

            # Then use XDG config
            # This includes both the user config and
            # /etc/xdg/mycroft/mycroft.conf
            for conf_dir in xdg.BaseDirectory.load_config_paths('core'):
                configs.append(LocalConf(join(conf_dir, 'core.conf')))

            # Then check the old user config
            # if isfile(OLD_USER_CONFIG):
                # _log_old_location_deprecation()
                # configs.append(LocalConf(OLD_USER_CONFIG))

            # Then use the system config (/etc/mycroft/mycroft.conf)
            configs.append(LocalConf(SYSTEM_CONFIG))

            # Then use remote config
            if remote:
                configs.append(RemoteConf())

            # Then use the config that comes with the package
            configs.append(LocalConf(DEFAULT_CONFIG))

            # Make sure we reverse the array, as merge_dict will put every new
            # file on top of the previous one
            configs = reversed(configs)
        else:
            # Handle strings in stack
            for index, item in enumerate(configs):
                if isinstance(item, str):
                    configs[index] = LocalConf(item)

        # Merge all configs into one
        base = {}
        for c in configs:
            merge_dict(base, c)

        # copy into cache
        if cache:
            Configuration.__config.clear()
            for key in base:
                Configuration.__config[key] = base[key]
            return Configuration.__config
        else:
            return base

    @staticmethod
    def set_config_update_handlers(bus):
        """Setup websocket handlers to update config.

        Args:
            bus: Message bus client instance
        """
        bus.on("configuration.updated", Configuration.updated)
        bus.on("configuration.patch", Configuration.patch)
        bus.on("configuration.patch.clear", Configuration.patch_clear)

    @staticmethod
    def updated(message):
        """Handler for configuration.updated,

        Triggers an update of cached config.
        """
        Configuration.load_config_stack(cache=True)

    @staticmethod
    def patch(message):
        """Patch the volatile dict usable by skills

        Args:
            message: Messagebus message should contain a config
                     in the data payload.
        """
        config = message.data.get("config", {})
        merge_dict(Configuration.__patch, config)
        Configuration.load_config_stack(cache=True)

    @staticmethod
    def patch_clear(message):
        """Clear the config patch space.

        Args:
            message: Messagebus message should contain a config
                     in the data payload.
        """
        Configuration.__patch = {}
        Configuration.load_config_stack(cache=True)
