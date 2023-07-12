import os
from os.path import join, dirname

import xdg.BaseDirectory
from xdg.BaseDirectory import xdg_config_home

# def get_xdg_config_save_path(folder=None):
#     """ return base XDG config save path taking into account ovos.conf """
#     folder = folder or "core"
#     print(xdg_config_home)
#     return join(xdg_config_home(), 'core')

DEFAULT_CONFIG = join(dirname(__file__), 'core.conf')
SYSTEM_CONFIG = os.environ.get('MYCROFT_SYSTEM_CONFIG',
                               '/etc/core/core.conf')
USER_CONFIG = join(xdg.BaseDirectory.xdg_config_home,
                   'core',
                   'core.conf'
                   )

REMOTE_CONFIG = "mycroft.ai"
WEB_CONFIG_CACHE = os.environ.get('MYCROFT_WEB_CACHE',
                                  '/var/tmp/mycroft_web_cache.json')
