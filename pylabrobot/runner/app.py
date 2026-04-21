"""FastAPI application for the PyLabRobot Protocol Runner."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pylabrobot.resources import Resource
from pylabrobot.runner.deck_bridge import DeckBridge
from pylabrobot.runner.executor import ExecutionState, ProtocolExecutor
from pylabrobot.runner.protocol_store import STARTER_TEMPLATE, ProtocolStore

logger = logging.getLogger(__name__)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


class SaveProtocolRequest(BaseModel):
  code: str


class RunProtocolRequest(BaseModel):
  code: str


def create_app(root_resource: Resource, device: Any = None) -> FastAPI:
  app = FastAPI(title="PyLabRobot Runner")
  bridge = DeckBridge(root_resource)
  store = ProtocolStore()

  def on_output(text: str, stream: str) -> None:
    msg = bridge._make_event("console_output", {"text": text, "stream": stream})
    import asyncio
    try:
      loop = asyncio.get_running_loop()
      loop.create_task(bridge._broadcast(msg))
    except RuntimeError:
      pass

  executor = ProtocolExecutor(on_output=on_output)

  app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

  @app.get("/", response_class=HTMLResponse)
  async def index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), "r", encoding="utf-8") as f:
      return f.read()

  @app.get("/api/deck")
  async def get_deck():
    from pylabrobot.runner.deck_bridge import _serialize_with_methods

    return _serialize_with_methods(root_resource)

  @app.get("/api/deck/state")
  async def get_deck_state():
    state: Dict[str, Any] = {}

    def collect(resource: Resource) -> None:
      s = resource.serialize_state()
      if s is not None:
        state[resource.name] = s
      for child in resource.children:
        collect(child)

    collect(root_resource)
    return state

  # ============== Protocol CRUD ==============

  @app.get("/api/protocols")
  async def list_protocols():
    return {"protocols": store.list_protocols()}

  @app.get("/api/protocols/{name}")
  async def get_protocol(name: str):
    if not store.exists(name):
      raise HTTPException(status_code=404, detail=f"Protocol '{name}' not found")
    return {"name": name, "code": store.load(name)}

  @app.post("/api/protocols/{name}")
  async def save_protocol(name: str, body: SaveProtocolRequest):
    store.save(name, body.code)
    return {"name": name, "saved": True}

  @app.delete("/api/protocols/{name}")
  async def delete_protocol(name: str):
    if not store.exists(name):
      raise HTTPException(status_code=404, detail=f"Protocol '{name}' not found")
    store.delete(name)
    return {"name": name, "deleted": True}

  @app.get("/api/protocols/_starter")
  async def get_starter():
    return {"code": STARTER_TEMPLATE}

  # ============== Execution ==============

  @app.post("/api/run")
  async def run_protocol(body: RunProtocolRequest):
    if executor.state == ExecutionState.RUNNING:
      raise HTTPException(status_code=409, detail="A protocol is already running")
    if device is None:
      raise HTTPException(status_code=400, detail="No device configured")

    import asyncio

    asyncio.create_task(executor.run(body.code, device))
    return {"status": "started"}

  @app.get("/api/run/status")
  async def run_status():
    return {"state": executor.state.value, "error": executor.error}

  @app.post("/api/run/stop")
  async def run_stop():
    executor.stop()
    return {"status": "stopping"}

  # ============== WebSocket ==============

  @app.websocket("/ws")
  async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await bridge.add_client(ws)
    logger.warning("WebSocket client connected")
    try:
      while True:
        data = await ws.receive_text()
        msg = json.loads(data)
        logger.warning("WS received: %s", msg.get("event", msg))
        if msg.get("event") == "ready":
          logger.warning("Sending initial state to client...")
          await bridge._send_initial_state(ws)
          logger.warning("Initial state sent")
    except WebSocketDisconnect:
      logger.warning("WebSocket client disconnected")
      bridge.remove_client(ws)
    except Exception as e:
      logger.warning("WebSocket error: %s", e)
      bridge.remove_client(ws)

  return app
