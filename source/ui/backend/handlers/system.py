import json
from typing import Dict, Optional

from fastapi import HTTPException, status

from source.ui.backend.common.typing import JSONStructure
from source.ui.backend.common.utils import sanitize, ws_send
from source.ui.backend.config import get_settings
from source.ui.backend.models.system import Config, Prompt
from source.util.log import LOG

settings = get_settings()


# TODO: Authenticate settings
def get_config(sort: Optional[bool] = False, core: Optional[bool] = False) -> Config:
    """Retrieves local or core configuration by leveraging the
    core-api skill

    Send `"core.api.config` message and wait for `core.api.config.answer`
    message to appear on the bus.

    :param sort: Sort alphabetically the configuration
    :type sort: bool, optional
    :param core: Retrieve the core configuration
    :type core: bool, optional
    :return: Return configuration
    :rtype: Config
    """
    status_code: int = status.HTTP_400_BAD_REQUEST
    msg: str = "unable to retrieve configuration"
    try:
        payload: Dict = {
            "type": "core.api.config",
            "data": {"app_key": settings.app_key, "core": core},
        }
        # if requirements():
        config: JSONStructure = ws_send(payload, "core.api.config.answer")
        if config["context"]["authenticated"]:
            if sort:
                config = json.loads(json.dumps(config, sort_keys=True))
            return sanitize(config["data"])
            status_code = status.HTTP_401_UNAUTHORIZED
            msg = "unable to authenticate with core-api skill"
            raise Exception
        status_code = status.HTTP_401_UNAUTHORIZED
        msg = "core-api skill is not installed on CORE"
        raise Exception
    except Exception as err:
        raise HTTPException(status_code=status_code, detail=msg) from err


def reload_config() -> status:
    """Reload configuration

    Send `configuration.updated` message to the bus, services will reload
    the configuration file.

    :return: Return HTTP 204 or 400
    :rtype: int
    """
    try:
        payload: Dict = {"type": "configuration.updated"}
        ws_send(payload)
        return status.HTTP_204_NO_CONTENT
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unable to reload the configuration ",
        ) from err


def set_config(config: Config):
    """
    Set configuration

    Send `configuration.pathced` message to the bus, services will modify configuration
    and save locally"""

    try:
        payload: Dict = {"type": "core.api.set.config", "data": {"config": config}}
        ws_send(payload)
        return status.HTTP_201_CREATED
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unable to set configuration",
        ) from err


def generate_response(prompt: Prompt):
    """Generate a response based on the provided prompt

    :param prompt: The prompt to generate a response from
    :type prompt: str
    :return: Generated response
    :rtype: JSONResponse
    """
    try:
        # Add code here to generate a response based on the provided prompt
        payload: Dict = {
            "type": "core.api.generate",
            "data": {"prompt": prompt.content},
        }
        response = ws_send(payload, "core.api.generate.response")
        # response = "Generated response based on the prompt: " + prompt
        LOG.info(f"generated response: {response}")
        return {"response": response.get("data", {}).get("response")}
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating response",
        ) from err
