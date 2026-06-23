"""State query helpers for the Protocol Runner.

Extracts channel and arm state from a device instance.
Works with both simulation (chatterbox) and hardware backends.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_channel_states(device: Any) -> Dict[str, Any]:
  """Extract channel state from device.pip.

  Returns a dict with num_channels and per-channel state including
  tip presence, volume, and tip properties.
  """
  pip = getattr(device, "pip", None)
  if pip is None:
    return {"num_channels": 0, "channels": []}

  num_channels = pip.num_channels
  channels = []

  for i in range(num_channels):
    tracker = pip.head.get(i)
    if tracker is None or not tracker.has_tip:
      channels.append({
        "index": i,
        "has_tip": False,
        "tip": None,
        "volume": 0,
        "max_volume": 0,
        "pending_volume": 0,
      })
    else:
      tip = tracker.get_tip()
      vol = tip.tracker.get_used_volume() if tip.tracker else 0
      pending = tip.tracker.pending_volume if tip.tracker else 0
      max_vol = tip.maximal_volume

      tip_info = {
        "total_tip_length": tip.total_tip_length,
        "fitting_depth": tip.fitting_depth,
        "maximal_volume": tip.maximal_volume,
        "has_filter": tip.has_filter,
      }
      if hasattr(tip, "tip_type"):
        tip_info["tip_type"] = str(tip.tip_type.value) if hasattr(tip.tip_type, "value") else str(tip.tip_type)

      channels.append({
        "index": i,
        "has_tip": True,
        "tip": tip_info,
        "volume": round(vol, 2),
        "max_volume": round(max_vol, 2),
        "pending_volume": round(pending, 2),
      })

  return {"num_channels": num_channels, "channels": channels}


async def get_arm_states(device: Any) -> List[Dict[str, Any]]:
  """Extract arm position and state from device.

  Returns a list of arm state dicts. Queries the backend for
  current position (works for both simulation and hardware).
  """
  arms = []

  arm = getattr(device, "arm", None)
  if arm is not None:
    arm_info: Dict[str, Any] = {
      "name": "arm",
      "type": type(arm).__name__,
      "available": True,
      "holding": arm.holding,
      "held_resource": None,
    }

    if arm.holding and arm._picked_up is not None:
      arm_info["held_resource"] = arm._picked_up.resource.name

    try:
      loc = await arm.get_gripper_location()
      arm_info["position"] = {
        "x": round(loc.location.x, 1),
        "y": round(loc.location.y, 1),
        "z": round(loc.location.z, 1),
      }
      arm_info["rotation"] = {
        "x": round(loc.rotation.x, 1),
        "y": round(loc.rotation.y, 1),
        "z": round(loc.rotation.z, 1),
      }
    except Exception:
      arm_info["position"] = {"x": 0, "y": 0, "z": 0}
      arm_info["rotation"] = {"x": 0, "y": 0, "z": 0}

    try:
      backend = arm.backend
      if hasattr(backend, "_gripper_width"):
        arm_info["gripper_width"] = round(backend._gripper_width, 1)
      if hasattr(backend, "_closed"):
        arm_info["gripper_closed"] = backend._closed
    except Exception:
      pass

    arms.append(arm_info)

  return arms
