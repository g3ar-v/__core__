"""Super class of HTTPBearer from FastAPI to handle Bearer token
"""
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError

from source.ui.backend.config import get_settings

from .handlers import decode_jwt, get_user

settings = get_settings()


class JWTBearer(HTTPBearer):
    """Override HTTPBearer class"""

    def __init__(self, auto_error: bool = False):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        creds: HTTPAuthorizationCredentials = await super().__call__(request)

        if creds:
            if not creds.scheme == "Bearer":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid authentication scheme",
                )
            self.verify_access_jwt(creds.credentials)

    @classmethod
    def verify_access_jwt(cls, jwt_token: str) -> bool:
        """Verify the JWT token

        The JWT token is decoded and checked for a `user` key, if this key is
        found then it campares the value with the `default_admin` option
        from `config.py`.

        :param jwt_token: JWT token to verify
        :type jwt_token: str
        :return: Return True or False
        :rtype: bool
        """
        try:
            payload: dict = decode_jwt(jwt_token)
            if get_user(payload["sub"]) and payload["scope"] == "access":
                return True
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid scope for token",
            )
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="access token expired"
            )
        except InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid access token"
            )

    @classmethod
    def verify_refresh_jwt(cls, jwt_token: str) -> bool:
        """Verify the JWT token

        The JWT token is decoded and checked for a `user` key, if this key is
        found then it campares the value with the `default_admin` option
        from `config.py`.

        :param jwt_token: JWT token to verify
        :type jwt_token: str
        :return: Return True or False
        :rtype: bool
        """
        try:
            payload: dict = decode_jwt(jwt_token)
            if get_user(payload["sub"]) and payload["scope"] == "refresh":
                return True
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid scope for token",
            )
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token expired"
            )
        except InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token"
            )
