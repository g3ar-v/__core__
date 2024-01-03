"""Application entrypoint
"""
from fastapi import (
    FastAPI,
    status,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
)
from typing import List, Dict

# from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from .config import get_settings
from .routers import voice, system
from .common.utils import websocket_manager, ws_send

settings = get_settings()


def custom_openapi_schema() -> dict:
    """Customize the OpenAPI schema

    :return: Return the customized OpenAPI schema
    :rtype: dict
    """
    openapi_schema = get_openapi(
        title=settings.app_name,
        version=settings.app_version,
        routes=app.routes,
    )
    openapi_schema["info"] = {
        "title": settings.app_name,
        "version": settings.app_version,
        "description": "API to connect to AI message bus system.",
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.openapi = custom_openapi_schema
# websocket_manager = WebSocketManager()


# NOTE: should this be the path?
# this should only work if core-skills is alive or running
@app.get("/v1/status")
async def get_status():
    try:
        payload: Dict = {"type": "core.skills.is_alive"}
        response = ws_send(payload, "core.skills.is_alive.response")
        messagebus_active = response.get("data", {}).get("status", {})

        # ws_send will throw error if it can't get to messagebus
        if messagebus_active is True:
            return {"status": True, "version": settings.prefix_version}

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="unable to fetch status"
        ) from error

        print(error)


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
):
    await websocket_manager.connect(websocket)

    try:
        data = await websocket.receive_text()
        # Do something with data
    except WebSocketDisconnect:
        await websocket_manager.disconnect(websocket)


# app.include_router(auth.router, prefix=settings.prefix_version)
# app.include_router(skills.router, prefix=settings.prefix_version)
app.include_router(system.router, prefix=settings.prefix_version)
app.include_router(voice.router, prefix=settings.prefix_version)
# app.include_router(network.router, prefix=settings.prefix_version)
