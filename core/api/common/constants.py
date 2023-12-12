"""Contants used by different components of this application
"""
from typing import List, Dict

API_SKILL_ID: str = "core-api-skill"
SANITIZE_KEY_LIST: List = ["password", "key", "code", "username",
                           "access_key_id", "secret_access_key"]
JWT_SCOPES: Dict = {
    "access": "access",
    "refresh": "refresh"
}
JWT_ISSUER: str = "core-api"
