import os
from os.path import dirname, join

# import xdg.BaseDirectory
from xdg.BaseDirectory import xdg_config_home


def get_core_config_dir(folder=None):
    """return base XDG config save path"""
    folder = folder or "core"
    return join(xdg_config_home, folder)


DEFAULT_CONFIG = join(dirname(__file__), "core.conf")
# TODO: find where this is set in core-setup
SYSTEM_CONFIG = os.environ.get("CORE_SYSTEM_CONFIG", "/etc/core/core.conf")
USER_CONFIG = join(xdg_config_home, "core", "core.conf")

# REMOTE_CONFIG = "mycroft.ai"
# WEB_CONFIG_CACHE = os.environ.get('MYCROFT_WEB_CACHE',
#                                   '/var/tmp/mycroft_web_cache.json')
