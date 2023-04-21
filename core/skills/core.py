""" Collection of core functions of the mycroft skills system.

This file is now depricated and skill should now import directly from
mycroft.skills.
"""
# Import moved methods for backwards compatibility
# This will need to remain here for quite some time since removing it
# would break most of the skills out there.
import core.skills.mycroft_skill as mycroft_skill
import core.skills.fallback_skill as fallback_skill
from .mycroft_skill import *  # noqa


class MycroftSkill(mycroft_skill.MycroftSkill):
    # Compatibility, needs to be kept for a while to not break every skill
    pass


class FallbackSkill(fallback_skill.FallbackSkill):
    # Compatibility, needs to be kept for a while to not break every skill
    pass
