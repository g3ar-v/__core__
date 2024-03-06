import asyncio
import json
from typing import Dict

import websockets

from core.util.log import LOG

bus = None
ws = None
queue = asyncio.Queue()


# TODO: generate a decorator that converts sync to async
def async_wrapper(coroutine, payload):
    async def wrapper(*args, **kwargs):
        await ws.send(json.dumps(payload))


async def handle_websocket(websocket, path):
    global ws

    while True:
        try:
            ws = websocket

            while True:
                try: 
                    message = queue.get_nowait()

                except asyncio.QueueEmpty:
                    continue

                if message is None:
                    continue

                LOG.info(f"message: {message}")
                await ws.send(json.dumps(message))
                # LOG.info(f"websocket: {ws} and {websocket}")

            message = await websocket.recv()
            print(f"Received message: {message}")
            # Process the received message as needed
            # You can send a response back using await websocket.send(response)
        except websockets.ConnectionClosedOK:
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
    async def handle_utt(event):
        if event.data.get("context", {}).get("source", {}) != "ui_backend":
            utterance = event.data.get("utterances", [])[0]
            payload: Dict = {"role": "user", "content": utterance}
            await ws.send(json.dumps(payload))

    asyncio.run(handle_utt(event))


def handle_utterance_response(event):
        payload: Dict = event.data.get("content", {})
        queue.put_nowait(payload)