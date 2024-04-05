"""Models related to voice
"""
from typing import List, Optional

from pydantic import BaseModel


class Speak(BaseModel):
    """Model for speaking POST action"""

    utterance: str
    lang: Optional[str] = None


class Message(BaseModel):
    """Model for sending message via POST action"""

    content: Optional[str]
    role: str


class ContextData(BaseModel):
    """Model for context data"""

    context: List[Message]


class MicState(BaseModel):
    """Model for mic state"""

    state: str
