"""Functions use multiple times in different places across the application
"""
import asyncio
import json
from time import time
from typing import Dict, List, Optional

from fastapi import WebSocket
from websocket import WebSocketException, WebSocketTimeoutException, create_connection

from core.ui.backend.common import constants
from core.ui.backend.common.typing import JSONStructure
from core.ui.backend.config import get_settings

settings = get_settings()


# TODO: find out if this exits in codebase
def ws_send(
    payload: JSONStructure, wait_for_message: Optional[str] = None
) -> JSONStructure:
    """Handles websocket interactions, from the connection,
    the send/receive message and the closing.

    :param payload: JSON dict to send to the bus
    :type payload: dict
    :param wait_for_message: Message to wait for from the bus
    :type wait_for_message: str, optional
    :return: Return the received message or and empty dict if nothing to retrun
    :rtype: JSONStructure
    """
    websocket = None
    try:
        websocket = create_connection(
            url=settings.ws_uri, timeout=settings.ws_conn_timeout
        )
    except WebSocketTimeoutException as err:
        return err

    try:
        # If message is expected as answer then we enter in a loop. The loop
        # will timeout after 3 seconds if no message equal to wait_for_message
        # is received.
        if wait_for_message:
            timeout_start: float = time()
            data: Dict = {}
            websocket.send(json.dumps(payload))
            while time() < timeout_start + settings.ws_recv_timeout:
                recv: JSONStructure = json.loads(websocket.recv())
                if recv["type"] == wait_for_message and recv["data"]:
                    data = recv
                    break
                # Check for authentication if required.
                if (
                    recv["type"] == wait_for_message
                    and not recv["context"]["authenticated"]
                ):
                    data = recv
                    break
            websocket.close()
            return data

        # Send message without wait for message and return an empty JSON dict.
        websocket.send(json.dumps(payload))
        websocket.close()
        return {}
    except WebSocketException as err:
        websocket.close()
        return err


def sanitize(data: JSONStructure) -> JSONStructure:
    """Sanitizes JSON dictionnary to avoid data leaking.

    By default, `password`, `key, `code` and `username` are keys that will
    be popped-out from the dict.

    :param data: JSON dictionnary to sanitize
    :type data: JSONStructure
    :return: Sanitized JSON dictionanry
    :rtype: JSONStructure
    """
    if settings.hide_sensitive_data:
        keys: List = constants.SANITIZE_KEY_LIST
        for key in keys:
            data.pop(key, None)
        return data
    return data


active_connections: List[WebSocket] = []


def get_active_connections():
    return active_connections


async def send_message_to_clients(message: str, active_connections):
    try:
        for conn in active_connections:
            print(message.__dict__)
            await conn.send_json(message.__dict__)
        return {}
    except Exception as e:
        raise e


class WebSocketManager:
    def __init__(self):
        self.active_websockets: List[WebSocket] = []
        self.queue: asyncio.Queue = asyncio.Queue()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_websockets.append(websocket)
        asyncio.create_task(self.sender(websocket))

    async def disconnect(self, websocket: WebSocket):
        self.active_websockets.remove(websocket)

    async def send_data(self, data: str):
        await self.queue.put(data)

    async def sender(self, websocket: WebSocket):
        while True:
            try:
                data = await self.queue.get()
                print(f"websocket state {websocket.client_state}")

                await websocket.send_json(data)
            except Exception as e:
                print(f"Error in sender: {e}")
                print(f"disconnecting websocket: {websocket}")
                await self.disconnect(websocket)
                break


websocket_manager = WebSocketManager()
