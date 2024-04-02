import asyncio
import json
from typing import Dict

import websockets

from core.util.log import LOG

bus = None
ws = None
queue = asyncio.Queue()


# TODO: generate a decorator that converts sync to async
# def async_wrapper(coroutine, payload):
#     async def wrapper(*args, **kwargs):
#         await ws.send(json.dumps(payload))


async def handle_websocket(websocket, path):
    global ws
    ws = websocket

    while True:
        try:
            # Wait for a message with a timeout, to periodically check for websocket
            # closure
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No message within timeout period, continue to check for websocket
                # closure
                continue

            if message is None:
                continue

            # LOG.info(f"message: {message}")
            await ws.send(json.dumps(message))
            # LOG.info(f"websocket: {ws} and {websocket}")

            # message = await websocket.recv()
        except websockets.ConnectionClosedOK:
            # Properly handle the connection closed exception
            LOG.info("Websocket connection closed gracefully")
            break
        except Exception as e:
            # Handle other exceptions that may occur
            LOG.error(f"Unexpected error: {e}")
            break


start_server = websockets.serve(handle_websocket, "0.0.0.0", 8081)


async def start_web_ui(messagebus):
    global bus

    bus = messagebus
    bus.on("recognizer_loop:audio_output_start", handle_audio_start)
    bus.on("recognizer_loop:audio_output_end", handle_audio_end)
    bus.on("recognizer_loop:record_begin", handle_record_begin)
    bus.on("recognizer_loop:record_end", handle_record_end)
    bus.on("recognizer_loop:utterance", handle_utterance)
    bus.on("core.utterance.response", handle_utterance_response)

    async with start_server:
        await asyncio.Future()


def handle_audio_start(event):
    async def handle_audio(event):
        LOG.info("SENDING AUDIO START")

        payload: Dict = {
            "role": "status",
            "data": "recognizer_loop:audio_output_start",
        }

        await ws.send(json.dumps(payload))

    asyncio.run(handle_audio(event))


def handle_audio_end(event):
    async def handle_end(event):
        LOG.info("SENDING AUDIO END")

        payload: Dict = {
            "role": "status",
            "data": "recognizer_loop:audio_output_end",
        }

        await ws.send(json.dumps(payload))

    asyncio.run(handle_end(event))


def handle_record_begin(event):
    async def handle_begin(event):
        LOG.info("RECORDING STARTED")

        payload: Dict = {
            "role": "status",
            "data": "recognizer_loop:record_begin",
        }

        await ws.send(json.dumps(payload))

    asyncio.run(handle_begin(event))


def handle_record_end(event):
    async def handle_end_record(event):
        LOG.info("RECORDING ENDED")

        payload: Dict = {
            "role": "status",
            "data": "recognizer_loop:record_end",
        }

        await ws.send(json.dumps(payload))

    asyncio.run(handle_end_record(event))


def handle_utterance(event):
    """
    Handle the utterance event by sending it to the websocket client.

    If the source of the event is not 'ui_backend', this function extracts the
    first utterance from the event data and sends it as a JSON payload through
    the websocket connection. The payload consists of a role 'user' and the
    content of the utterance.

    Args:
        event: An object containing the event data with 'utterances' and 'context'.
    """
    async def handle_utt(event):
        if event.data.get("context", {}).get("source", {}) != "ui_backend":
            # LOG.info("sending utterance: " + str(event.data))

            utterance = event.data.get("utterances", [])[0]
            payload: Dict = {"role": "user", "content": utterance}
            await ws.send(json.dumps(payload))

    asyncio.run(handle_utt(event))


def handle_utterance_response(event):
    """
    Enqueue the utterance response payload into the asyncio queue.

    The function takes an event object, extracts the 'content' from the event's data,
    and puts it into the asyncio queue for later processing. This payload will
    eventually be sent to the websocket client.

    Args:
        event: An object containing the event data with the 'content' field.
    """
    payload: Dict = event.data.get("content", {})
    queue.put_nowait(payload)
