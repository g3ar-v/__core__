""" Mycroft skills module, collection of tools for building skills.

These classes, decorators and functions are used to build skills for Mycroft.
"""

# import core.
from .mycroft_skill import (MycroftSkill, intent_handler, intent_file_handler,
                            resting_screen_handler, skill_api_method)
from .intent_service import AdaptIntent
from .fallback_skill import FallbackSkill
from .common_iot_skill import CommonIoTSkill
from .common_play_skill import CommonPlaySkill, CPSMatchLevel
from .common_query_skill import CommonQuerySkill, CQSMatchLevel

__all__ = ['MycroftSkill',
           'intent_handler',
           'intent_file_handler',
           'resting_screen_handler',
           'FallbackSkill',
           'CommonIoTSkill',
           'CommonPlaySkill',
           'CPSMatchLevel',
           'CommonQuerySkill',
           'CQSMatchLevel']
