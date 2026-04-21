"""Bridge between the pylabrobot resource tree and websocket clients.

Registers callbacks on a root Resource and pushes serialized events
to all connected websocket clients using the same event protocol as
the existing pylabrobot Visualizer.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

from pylabrobot.__version__ import STANDARD_FORM_JSON_VERSION
from pylabrobot.resources import Resource

logger = logging.getLogger(__name__)


def _sanitize_floats(obj: Any) -> Any:
  if isinstance(obj, float):
    if math.isnan(obj) or math.isinf(obj):
      return None
    return obj
  if isinstance(obj, dict):
    return {k: _sanitize_floats(v) for k, v in obj.items()}
  if isinstance(obj, (list, tuple)):
    return [_sanitize_floats(v) for v in obj]
  return obj


def _serialize_with_methods(resource: Resource) -> dict:
  data = resource.serialize()
  from pylabrobot.visualizer.visualizer import _get_public_methods

  data["methods"] = _get_public_methods(type(resource))
  if "children" in data:
    data["children"] = [_serialize_with_methods(child) for child in resource.children]
  return data


class DeckBridge:
  """Adapts resource tree callbacks to websocket event broadcasts."""

  def __init__(self, root: Resource):
    self._root = root
    self._clients: Set[WebSocket] = set()
    self._id = 0
    self._pending_state_updates: Dict[str, dict] = {}

    root.register_did_assign_resource_callback(self._on_resource_assigned)
    root.register_did_unassign_resource_callback(self._on_resource_unassigned)
    self._register_state_callbacks(root)

  def _register_state_callbacks(self, resource: Resource) -> None:
    resource.register_state_update_callback(
      lambda _: self._on_state_update(resource)
    )
    for child in resource.children:
      self._register_state_callbacks(child)

  def _generate_id(self) -> str:
    self._id += 1
    return str(self._id)

  def _make_event(self, event: str, data: Dict[str, Any]) -> str:
    return json.dumps(
      _sanitize_floats(
        {
          "id": self._generate_id(),
          "version": STANDARD_FORM_JSON_VERSION,
          "data": data,
          "event": event,
        }
      )
    )

  async def add_client(self, ws: WebSocket) -> None:
    self._clients.add(ws)

  def remove_client(self, ws: WebSocket) -> None:
    self._clients.discard(ws)

  async def _send_initial_state(self, ws: WebSocket) -> None:
    msg = self._make_event(
      "set_root_resource",
      {"resource": _serialize_with_methods(self._root)},
    )
    await ws.send_text(msg)

    state: Dict[str, Any] = {}

    def collect_state(resource: Resource) -> None:
      s = resource.serialize_state()
      if s is not None:
        state[resource.name] = s
      for child in resource.children:
        collect_state(child)

    collect_state(self._root)
    msg = self._make_event("set_state", state)
    await ws.send_text(msg)

  async def _broadcast(self, message: str) -> None:
    dead: List[WebSocket] = []
    for ws in self._clients:
      try:
        await ws.send_text(message)
      except Exception:
        dead.append(ws)
    for ws in dead:
      self._clients.discard(ws)

  def _on_resource_assigned(self, resource: Resource) -> None:
    self._register_state_callbacks(resource)
    data = {
      "resource": _serialize_with_methods(resource),
      "state": resource.serialize_all_state(),
      "parent_name": resource.parent.name if resource.parent else None,
    }
    msg = self._make_event("resource_assigned", data)
    import asyncio

    try:
      loop = asyncio.get_running_loop()
      loop.create_task(self._broadcast(msg))
    except RuntimeError:
      pass

  def _on_resource_unassigned(self, resource: Resource) -> None:
    data = {"resource_name": resource.name}
    msg = self._make_event("resource_unassigned", data)
    import asyncio

    try:
      loop = asyncio.get_running_loop()
      loop.create_task(self._broadcast(msg))
    except RuntimeError:
      pass

  def _on_state_update(self, resource: Resource) -> None:
    state = resource.serialize_state()
    self._pending_state_updates[resource.name] = state
    import asyncio

    try:
      loop = asyncio.get_running_loop()
      loop.create_task(self._flush_state_updates())
    except RuntimeError:
      pass

  async def _flush_state_updates(self) -> None:
    if not self._pending_state_updates:
      return
    data = self._pending_state_updates
    self._pending_state_updates = {}
    msg = self._make_event("set_state", data)
    await self._broadcast(msg)
