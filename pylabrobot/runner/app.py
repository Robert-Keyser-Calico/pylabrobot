"""FastAPI application for the PyLabRobot Protocol Runner."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pylabrobot.resources import Resource
from pylabrobot.runner.assistant import Assistant
from pylabrobot.runner.deck_bridge import DeckBridge
from pylabrobot.runner.device_manager import ConnectionState, DeviceManager, DeviceMode
from pylabrobot.runner.executor import ExecutionState, ProtocolExecutor
from pylabrobot.runner.state_queries import get_arm_states, get_channel_states
from pylabrobot.runner.protocol_store import STARTER_TEMPLATE, ProtocolStore

logger = logging.getLogger(__name__)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


# ============== Request / Response Models ==============


class SaveProtocolRequest(BaseModel):
  code: str = Field(..., description="Python protocol source code")


class RunProtocolRequest(BaseModel):
  code: str = Field(..., description="Python protocol source code to execute")


class ChatRequest(BaseModel):
  message: str = Field(..., description="Natural language request")
  editor_code: Optional[str] = Field(None, description="Current editor contents for context")


class ProtocolListResponse(BaseModel):
  protocols: List[str] = Field(..., description="List of saved protocol names")


class ProtocolResponse(BaseModel):
  name: str
  code: str


class SaveResponse(BaseModel):
  name: str
  saved: bool


class DeleteResponse(BaseModel):
  name: str
  deleted: bool


class StarterResponse(BaseModel):
  code: str = Field(..., description="Starter template code")


class RunResponse(BaseModel):
  status: str = Field(..., description="'started' if execution began")


class RunStatusResponse(BaseModel):
  state: str = Field(..., description="idle, running, completed, error, or stopped")
  error: Optional[str] = Field(None, description="Error message if state is 'error'")


class StopResponse(BaseModel):
  status: str = Field(..., description="'stopping' if cancellation requested")


class ChatResponse(BaseModel):
  code: str = Field(..., description="Generated Python code")


class ClearResponse(BaseModel):
  cleared: bool


class ConnectRequest(BaseModel):
  mode: str = Field("simulation", description="'simulation' or 'hardware'")


class ConnectResponse(BaseModel):
  status: str
  mode: str


class DisconnectResponse(BaseModel):
  status: str


class DeviceStatusResponse(BaseModel):
  state: str = Field(..., description="disconnected, connecting, connected, disconnecting, error")
  mode: str = Field(..., description="simulation or hardware")
  error: Optional[str] = None
  device_type: Optional[str] = None
  has_device: bool = False
  has_deck: bool = False


class DeviceConfigRequest(BaseModel):
  device_type: Optional[str] = Field(None, description="e.g. 'TecanEVO'")
  diti_count: Optional[int] = Field(None, description="Number of channels")
  air_liha: Optional[bool] = Field(None, description="Use Air LiHa (ZaapMotion)")
  has_roma: Optional[bool] = Field(None, description="Include RoMa arm")
  packet_read_timeout: Optional[int] = None
  read_timeout: Optional[int] = None
  write_timeout: Optional[int] = None


class DeviceConfigResponse(BaseModel):
  config: Dict[str, Any]


class ChannelInfo(BaseModel):
  index: int
  has_tip: bool
  tip: Optional[Dict[str, Any]] = None
  volume: float = 0
  max_volume: float = 0
  pending_volume: float = 0


class ChannelsResponse(BaseModel):
  num_channels: int
  channels: List[ChannelInfo]


class ArmPosition(BaseModel):
  x: float = 0
  y: float = 0
  z: float = 0


class ArmRotation(BaseModel):
  x: float = 0
  y: float = 0
  z: float = 0


class ArmInfo(BaseModel):
  name: str
  type: str
  available: bool = True
  position: ArmPosition = ArmPosition()
  rotation: ArmRotation = ArmRotation()
  holding: bool = False
  held_resource: Optional[str] = None
  gripper_width: Optional[float] = None
  gripper_closed: Optional[bool] = None


class ArmsResponse(BaseModel):
  arms: List[ArmInfo]


# ============== App Factory ==============


def create_app(
  google_api_key: Optional[str] = None,
  vertex_project: Optional[str] = None,
  vertex_location: str = "us-central1",
  vertex_model: str = "gemini-2.0-flash",
) -> FastAPI:
  app = FastAPI(
    title="PyLabRobot Runner",
    description=(
      "Protocol execution and deck visualization for PyLabRobot. "
      "Write protocols, run them in simulation or on real hardware, "
      "and observe deck state changes in real-time via WebSocket."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
  )

  from pylabrobot.resources.tecan.tecan_decks import EVO150Deck

  current_deck = EVO150Deck()
  current_device: Optional[Any] = None
  bridge = DeckBridge(current_deck)
  store = ProtocolStore()
  device_mgr = DeviceManager()
  state_polling_task: Optional[asyncio.Task] = None

  if google_api_key:
    logger.info("AI Assistant: using Google AI API key")
  elif vertex_project:
    logger.info("AI Assistant: using Vertex AI (project=%s)", vertex_project)
  else:
    logger.info("AI Assistant: no API key or Vertex project configured")

  assistant = Assistant(
    root_resource=current_deck,
    num_channels=8,
    api_key=google_api_key,
    project=vertex_project if not google_api_key else None,
    location=vertex_location,
    model=vertex_model,
  )

  def on_output(text: str, stream: str) -> None:
    msg = bridge._make_event("console_output", {"text": text, "stream": stream})
    import asyncio

    try:
      loop = asyncio.get_running_loop()
      loop.create_task(bridge._broadcast(msg))
    except RuntimeError:
      pass

  def on_deck_ready(deck: Any, device: Any) -> None:
    nonlocal current_deck, current_device
    current_deck = deck
    current_device = device
    bridge.set_root(deck)
    assistant._root = deck
    device_mgr.set_deck(deck)

  executor = ProtocolExecutor(on_output=on_output, on_deck_ready=on_deck_ready)

  app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

  # ============== UI ==============

  @app.get("/", response_class=HTMLResponse, include_in_schema=False)
  async def index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), "r", encoding="utf-8") as f:
      return f.read()

  # ============== Deck ==============

  @app.get("/api/deck", tags=["Deck"],
           summary="Get full deck resource tree",
           description="Returns the serialized resource tree including all carriers, "
           "plates, tip racks, and their positions.")
  async def get_deck():
    from pylabrobot.runner.deck_bridge import _serialize_with_methods

    return _serialize_with_methods(current_deck)

  @app.get("/api/deck/state", tags=["Deck"],
           summary="Get all resource states",
           description="Returns runtime state for every resource (volumes, tip presence, etc.).")
  async def get_deck_state():
    from pylabrobot.runner.deck_bridge import _sanitize_floats

    state: Dict[str, Any] = {}

    def collect(resource: Resource) -> None:
      s = resource.serialize_state()
      if s is not None:
        state[resource.name] = s
      for child in resource.children:
        collect(child)

    collect(current_deck)
    return _sanitize_floats(state)

  # ============== Protocols ==============

  @app.get("/api/protocols", tags=["Protocols"], response_model=ProtocolListResponse,
           summary="List saved protocols")
  async def list_protocols():
    return ProtocolListResponse(protocols=store.list_protocols())

  @app.get("/api/protocols/_starter", tags=["Protocols"], response_model=StarterResponse,
           summary="Get starter template",
           description="Returns a starter protocol template with deck setup and a sample run() function.")
  async def get_starter():
    return StarterResponse(code=STARTER_TEMPLATE)

  @app.get("/api/protocols/{name}", tags=["Protocols"], response_model=ProtocolResponse,
           summary="Load a saved protocol")
  async def get_protocol(name: str):
    if not store.exists(name):
      raise HTTPException(status_code=404, detail=f"Protocol '{name}' not found")
    return ProtocolResponse(name=name, code=store.load(name))

  @app.post("/api/protocols/{name}", tags=["Protocols"], response_model=SaveResponse,
            summary="Save a protocol",
            description="Save protocol source code to disk. Creates or overwrites.")
  async def save_protocol(name: str, body: SaveProtocolRequest):
    store.save(name, body.code)
    return SaveResponse(name=name, saved=True)

  @app.delete("/api/protocols/{name}", tags=["Protocols"], response_model=DeleteResponse,
              summary="Delete a saved protocol")
  async def delete_protocol(name: str):
    if not store.exists(name):
      raise HTTPException(status_code=404, detail=f"Protocol '{name}' not found")
    store.delete(name)
    return DeleteResponse(name=name, deleted=True)

  # ============== Execution ==============

  @app.post("/api/run", tags=["Execution"], response_model=RunResponse,
            summary="Run a protocol",
            description="Execute protocol code. If a device is connected via /api/device/connect, "
            "the protocol runs against that device. Otherwise a temporary simulated device "
            "is created. The script must define a `deck` variable and an "
            "`async def run(device):` function.")
  async def run_protocol(body: RunProtocolRequest):
    if executor.state == ExecutionState.RUNNING:
      raise HTTPException(status_code=409, detail="A protocol is already running")

    import asyncio

    managed = device_mgr.device if device_mgr.is_connected else None
    asyncio.create_task(executor.run(body.code, device=managed))
    return RunResponse(status="started")

  @app.get("/api/run/status", tags=["Execution"], response_model=RunStatusResponse,
           summary="Get execution status",
           description="Returns the current execution state and any error message.")
  async def run_status():
    return RunStatusResponse(state=executor.state.value, error=executor.error)

  @app.post("/api/run/stop", tags=["Execution"], response_model=StopResponse,
            summary="Stop running protocol",
            description="Cancel the currently running protocol. The protocol receives "
            "an asyncio.CancelledError.")
  async def run_stop():
    executor.stop()
    return StopResponse(status="stopping")

  # ============== Device Management ==============

  @app.get("/api/device/status", tags=["Device"], response_model=DeviceStatusResponse,
           summary="Get device connection status")
  async def device_status():
    return DeviceStatusResponse(**device_mgr.status_dict())

  @app.post("/api/device/connect", tags=["Device"], response_model=ConnectResponse,
            summary="Connect to a device",
            description="Connect to hardware or create a simulation device. "
            "The deck must be configured first by running a protocol script "
            "(which sets the deck variable). Use mode='simulation' for testing "
            "or mode='hardware' for real instruments.")
  async def device_connect(body: ConnectRequest):
    mode = DeviceMode(body.mode)
    try:
      await device_mgr.connect(mode)
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))

    if device_mgr.deck is not None:
      bridge.set_root(device_mgr.deck)

    return ConnectResponse(status="connected", mode=mode.value)

  @app.post("/api/device/disconnect", tags=["Device"], response_model=DisconnectResponse,
            summary="Disconnect from the device")
  async def device_disconnect():
    await device_mgr.disconnect()
    return DisconnectResponse(status="disconnected")

  @app.get("/api/device/config", tags=["Device"], response_model=DeviceConfigResponse,
           summary="Get current hardware configuration")
  async def device_get_config():
    return DeviceConfigResponse(config=device_mgr._hardware_config)

  @app.put("/api/device/config", tags=["Device"], response_model=DeviceConfigResponse,
           summary="Update hardware configuration",
           description="Update device parameters for hardware mode. Only provided "
           "fields are updated. Must be disconnected to change config.")
  async def device_set_config(body: DeviceConfigRequest):
    if device_mgr.is_connected:
      raise HTTPException(status_code=409, detail="Disconnect before changing config")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    device_mgr.set_hardware_config(updates)
    return DeviceConfigResponse(config=device_mgr._hardware_config)

  # ============== System State ==============

  @app.get("/api/channels", tags=["System State"], response_model=ChannelsResponse,
           summary="Get channel state",
           description="Returns tip presence, volume, and tip properties for all channels.")
  async def get_channels():
    dev = current_device or (device_mgr.device if device_mgr.is_connected else None)
    if dev is None:
      return ChannelsResponse(num_channels=0, channels=[])
    data = get_channel_states(dev)
    return ChannelsResponse(**data)

  @app.get("/api/arms", tags=["System State"], response_model=ArmsResponse,
           summary="Get arm positions",
           description="Returns position, rotation, and grip state for all configured arms.")
  async def get_arms():
    dev = current_device or (device_mgr.device if device_mgr.is_connected else None)
    if dev is None:
      return ArmsResponse(arms=[])
    arm_data = await get_arm_states(dev)
    return ArmsResponse(arms=[ArmInfo(**a) for a in arm_data])

  # State broadcasting during execution
  async def _broadcast_state_loop() -> None:
    """Poll channel and arm state every 500ms and broadcast to WebSocket clients."""
    while True:
      try:
        dev = current_device or (device_mgr.device if device_mgr.is_connected else None)
        if dev is not None and executor.state == ExecutionState.RUNNING:
          ch_data = get_channel_states(dev)
          ch_msg = bridge._make_event("channel_state", ch_data)
          await bridge._broadcast(ch_msg)

          arm_data = await get_arm_states(dev)
          arm_msg = bridge._make_event("arm_state", {"arms": arm_data})
          await bridge._broadcast(arm_msg)
      except Exception:
        pass
      await asyncio.sleep(0.5)

  @app.on_event("startup")
  async def start_state_broadcaster():
    nonlocal state_polling_task
    state_polling_task = asyncio.create_task(_broadcast_state_loop())

  # ============== AI Assistant ==============

  @app.post("/api/assistant/chat", tags=["AI Assistant"], response_model=ChatResponse,
            summary="Generate protocol code from natural language",
            description="Send a natural language description and optionally the current "
            "editor contents. Returns generated Python protocol code.")
  async def assistant_chat(body: ChatRequest):
    try:
      code = await assistant.chat(body.message, editor_code=body.editor_code)
      return ChatResponse(code=code)
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))

  @app.post("/api/assistant/clear", tags=["AI Assistant"], response_model=ClearResponse,
            summary="Clear conversation history")
  async def assistant_clear():
    assistant.clear_history()
    return ClearResponse(cleared=True)

  # ============== WebSocket ==============

  @app.websocket("/ws")
  async def websocket_endpoint(ws: WebSocket):
    """Real-time deck state updates.

    Events sent to client:
    - `set_root_resource` — full resource tree (on connect)
    - `set_state` — resource states (volumes, tips)
    - `resource_assigned` — new resource added to tree
    - `resource_unassigned` — resource removed from tree
    - `console_output` — protocol stdout/stderr output

    Client should send `{"event": "ready"}` after connecting to receive initial state.
    """
    await ws.accept()
    await bridge.add_client(ws)
    try:
      while True:
        data = await ws.receive_text()
        msg = json.loads(data)
        if msg.get("event") == "ready":
          await bridge._send_initial_state(ws)
    except WebSocketDisconnect:
      bridge.remove_client(ws)
    except Exception:
      bridge.remove_client(ws)

  return app
