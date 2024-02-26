from typing import Any, Optional

from pydantic import BaseModel


class Config(BaseModel):
    """Model configuration output"""

    key: Any


class ConfigResults(BaseModel):
    """Model configuration output"""

    results: Config


class Prompt(BaseModel):
    """Model for sending event status"""

    content: Optional[str] = None


class Message(BaseModel):
    """Model for sending message via POST action"""

    content: Optional[str] = None
    role: str = None
