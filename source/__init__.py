# Expose core  modules to skills and other programs
from os.path import abspath, dirname, join

from source.core import (FallbackSkill, Skill, intent_file_handler,
                         intent_handler)
from source.core.context import adds_context, removes_context
from source.intent_services import AdaptIntent
# from core.api import Api
from source.messagebus.message import Message
from source.util.log import LOG

CORE_ROOT_PATH = abspath(join(dirname(__file__), '..'))

__all__ = ['CORE_ROOT_PATH',
           'Api',
           'Message',
           'adds_context',
           'removes_context',
           'Skill',
           'FallbackSkill',
           'intent_handler',
           'intent_file_handler',
           'AdaptIntent']

LOG.init()  # read log level from config
