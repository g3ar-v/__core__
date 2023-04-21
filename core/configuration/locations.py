import os
from os.path import join, dirname, expanduser

import xdg.BaseDirectory

DEFAULT_CONFIG = join(dirname(__file__), 'mycroft.conf')
SYSTEM_CONFIG = os.environ.get('MYCROFT_SYSTEM_CONFIG',
                               '/etc/mycroft/mycroft.conf')
USER_CONFIG = join(xdg.BaseDirectory.xdg_config_home,
                   'mycroft',
                   'mycroft.conf'
                   )

REMOTE_CONFIG = "mycroft.ai"
WEB_CONFIG_CACHE = os.environ.get('MYCROFT_WEB_CACHE',
                                  '/var/tmp/mycroft_web_cache.json')
