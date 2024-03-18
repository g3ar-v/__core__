from typing import Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, status
from fastapi.responses import JSONResponse, Response

from core.ui.backend.auth.bearer import JWTBearer
from core.ui.backend.common.utils import websocket_manager
from core.ui.backend.handlers import system
from core.ui.backend.models.system import ConfigResults, Message, Prompt
from core.util.log import LOG

router = APIRouter(prefix="/system", tags=["system"])


@router.get(
    "/config",
    response_model=ConfigResults,
    summary="Collect local or core configuration",
    description="Send `core.api.config` message to the bus and wait \
        for `core.api.config.answer` response. This route leverage the \
        `core-api` skill.",
    response_description="Retrieved configuration",
    dependencies=[Depends(JWTBearer())],
)
async def config(
    sort: Optional[bool] = Query(
        default=True, description="Sort alphabetically the settings"
    ),
    core: Optional[bool] = Query(
        default=False, description="Display the core configuration"
    ),
) -> JSONResponse:
    """Collect local or core configuration

    :param sort: Sort alphabetically the configuration
    :type sort: bool, optional
    :param core: Retrieve merged configuration
    :type core: bool, optional
    :return: Return the configuration
    :rtype: JSONResponse
    """
    return JSONResponse(content=system.get_config(sort, core))


@router.put(
    "/config",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Notify services about configuration change",
    description="Send `configuration.updated` message to the bus, services \
        will reload the configuration file.",
    response_description="Configuration has been reloaded",
    dependencies=[Depends(JWTBearer())],
)
async def reload_config() -> Response:
    """Reload configuration

    :return: Return status code
    :rtype: int
    """
    return Response(status_code=system.reload_config())


@router.post(
    "/ai/utterance",
    response_model=Message,
    status_code=status.HTTP_201_CREATED,
    summary="send system utterance to UI",
    description="Send system utterance to UI",
    response_description="system utterance sent",
    dependencies=[Depends(JWTBearer())],
)
async def send_system_utterance(
    message: Message = Body(
        default=None,
        description="Message to send to UI",
        example='{"role": "system", "content": "hey there"}',
    ),
) -> JSONResponse:
    """Request to start the recording

    :return: HTTP status code
    :rtype: int
    """
    LOG.info("SENDING MESSAGE TO UI: %s", message.__dict__)
    await websocket_manager.send_data(message.__dict__)
    return JSONResponse(content={})


@router.post(
    "/config/set",
    response_model=ConfigResults,
    status_code=status.HTTP_201_CREATED,
    summary="set configuration",
    description="Set configuration",
    response_description="configuration set",
    dependencies=[Depends(JWTBearer())],
)
async def set_configuration(
    config: Dict = Body(
        default=None,
        description="Configuration to set",
        example='{"confirm_listening": false }',
    ),
) -> JSONResponse:
    """Request to set the configuration

    :return: HTTP status code
    :rtype: int
    """
    LOG.info("SETTING CONFIGURATION: %s", config)
    return JSONResponse(content=system.set_config(config))


@router.post(
    "/generate",
    status_code=status.HTTP_200_OK,
    summary="Generate response based on prompt",
    description="Generate a response based on the provided prompt",
    response_description="Response generated successfully",
    dependencies=[Depends(JWTBearer())],
)
async def generate_response(
    prompt: Prompt = Body(
        default=None,
        description="Message to send to UI",
        example='{ "content": "Create a concise, 3-5 word phrase as a header for the following query,\
      strictly adhering to the 3-5 word limit and avoiding the use of the word `title`: \
        what is the purpose of chemistry in the universe?"}',
    ),
) -> JSONResponse:
    """Generate a response based on the provided prompt

    :param prompt: The prompt to generate a response from
    :type prompt: str
    :return: Generated response
    :rtype: JSONResponse
    """
    return JSONResponse(content=system.generate_response(prompt))
