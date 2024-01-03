from typing import List

from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocket

from core.ui.backend.auth.bearer import JWTBearer
from core.ui.backend.common.utils import (
    websocket_manager,
    get_active_connections,
    send_message_to_clients,
)
from core.ui.backend.models.voice import Message
from core.util.log import LOG

router = APIRouter(prefix="/system", tags=["system"])


@router.post(
    "/user/utterance",
    response_model=Message,
    status_code=status.HTTP_201_CREATED,
    summary="send user utterance to UI",
    description="Send user utterance to UI",
    response_description="user utterance sent",
    dependencies=[Depends(JWTBearer())],
)
async def send_user_utterance(
    message: Message = Body(
        default=None,
        description="Message to send to UI",
        example='{"type": "user","prompt": "hey there"}',
    ),
) -> JSONResponse:
    """Request to start the recording

    :return: HTTP status code
    :rtype: int
    """
    LOG.info("Sending message to UI: %s", message.json())
    await websocket_manager.send_data(message.__dict__)
    return JSONResponse(content={})


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
        example='{"type": "system", "prompt": "hey there"}',
    ),
) -> JSONResponse:
    """Request to start the recording

    :return: HTTP status code
    :rtype: int
    """
    LOG.info("Sending message to UI: %s", message.json())
    await websocket_manager.send_data(message.__dict__)
    return JSONResponse(content={})
