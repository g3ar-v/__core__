from typing import Any
from pydantic import BaseModel


class Config(BaseModel):
    """Model configuration output"""

    key: Any


class ConfigResults(BaseModel):
    """Model configuration output"""

    results: Config
