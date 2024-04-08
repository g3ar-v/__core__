"""Keep the settingsmeta.json and settings.json files in sync with the backend.

The SkillSettingsMeta and SkillSettings classes run a synchronization every
minute to ensure the device and the server have the same values.

The settingsmeta.json file (or settingsmeta.yaml, if you prefer working with
yaml) in the skill's root directory contains instructions for the Selene UI on
how to display and update a skill's settings, if there are any.

For example, you might have a setting named "username".  In the settingsmeta
you can describe the interface to edit that value with:
    ...
    "fields": [
        {
            "name": "username",
            "type": "email",
            "label": "Email address to associate",
            "placeholder": "example@mail.com",
            "value": ""
        }
    ]
    ...

When the user changes the setting via the web UI, it will be sent down to all
the devices related to an account and automatically placed into
settings['username'].  Any local changes made to the value (e.g. via a verbal
interaction) will also be synchronized to the server to show on the web
interface.

The settings.json file contains name/value pairs for each setting.  There can
be entries in settings.json that are not related to those the user can
manipulate on the web.  There is logic in the SkillSettings class to ensure
these "hidden" settings are not affected when the synchronization occurs.  A
skill can define a function that will be called when any settings change.

SkillSettings Usage Example:
    from mycroft.skill.settings import SkillSettings

        s = SkillSettings('./settings.json', 'ImportantSettings')
        s.skill_settings['meaning of life'] = 42
        s.skill_settings['flower pot sayings'] = 'Not again...'
        s.save_settings()  # This happens automagically in a MycroftSkill
"""

import json
import re
from os.path import dirname
from pathlib import Path

from xdg.BaseDirectory import xdg_cache_home

from source.util import camel_case_split
from source.util.file_utils import ensure_directory_exists
from source.util.log import LOG

ONE_MINUTE = 60


def get_local_settings(skill_dir, skill_name) -> dict:
    """Build a dictionary using the JSON string stored in settings.json."""
    skill_settings = {}
    settings_path = Path(skill_dir).joinpath("settings.json")
    if settings_path.exists():
        with open(str(settings_path)) as settings_file:
            settings_file_content = settings_file.read()
        if settings_file_content:
            try:
                skill_settings = json.loads(settings_file_content)
            # TODO change to check for JSONDecodeError in 19.08
            except Exception:
                log_msg = "Failed to load {} settings from settings.json"
                LOG.exception(log_msg.format(skill_name))

    return skill_settings


def save_settings(skill_dir, skill_settings):
    """Save skill settings to file."""
    settings_path = Path(skill_dir).joinpath("settings.json")

    # Either the file already exists in /opt, or we are writing
    # to XDG_CONFIG_DIR and always have the permission to make
    # sure the file always exists
    if not Path(settings_path).exists():
        settings_path.touch(mode=0o644)

    with open(str(settings_path), "w") as settings_file:
        try:
            json.dump(skill_settings, settings_file)
        except Exception:
            LOG.exception("error saving skill settings to " "{}".format(settings_path))
        else:
            LOG.info("Skill settings successfully saved to " "{}".format(settings_path))


def get_display_name(skill_name: str):
    """Splits camelcase and removes leading/trailing "skill"."""
    skill_name = re.sub(r"(^[Ss]kill|[Ss]kill$)", "", skill_name)
    return camel_case_split(skill_name)


# Path to remote cache
REMOTE_CACHE = Path(xdg_cache_home, "core", "remote_skill_settings.json")


def load_remote_settings_cache():
    """Load cached remote skill settings.

    Returns:
        (dict) Loaded remote settings cache or None of none exists.
    """
    remote_settings = {}
    if REMOTE_CACHE.exists():
        try:
            with open(str(REMOTE_CACHE)) as cache:
                remote_settings = json.load(cache)
        except Exception as error:
            LOG.warning("Failed to read remote_cache ({})".format(error))
    return remote_settings


def save_remote_settings_cache(remote_settings):
    """Save updated remote settings to cache file.

    Args:
        remote_settings (dict): downloaded remote settings.
    """
    try:
        ensure_directory_exists(dirname(str(REMOTE_CACHE)))
        with open(str(REMOTE_CACHE), "w") as cache:
            json.dump(remote_settings, cache)
    except Exception as error:
        LOG.warning("Failed to write remote_cache. ({})".format(error))
    else:
        LOG.debug("Updated local cache of remote skill settings.")
