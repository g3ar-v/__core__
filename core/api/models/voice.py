"""Models related to voice
"""
from typing import Optional

from pydantic import BaseModel


class Speak(BaseModel):
    """Model for speaking POST action"""

    utterance: str
    lang: Optional[str] = None


class Message(BaseModel):
    """Model for sending message via POST action"""

    prompt: Optional[str] = None
