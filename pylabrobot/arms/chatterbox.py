"""Chatterbox backend for GripperArm (plate handling).

Logs operations without requiring hardware. Resource tracking
(plate assign/unassign) happens at the GripperArm level, so
simulation gets full plate movement tracking automatically.
"""

import asyncio
import logging
from typing import Optional

from pylabrobot.arms.backend import GripperArmBackend
from pylabrobot.arms.standard import GripperLocation
from pylabrobot.capabilities.capability import BackendParams
from pylabrobot.resources import Coordinate
from pylabrobot.resources.rotation import Rotation

logger = logging.getLogger(__name__)


class GripperArmChatterboxBackend(GripperArmBackend):
  """No-op GripperArm backend for simulation and testing."""

  def __init__(self, delay: float = 0.3):
    self._delay = delay
    self._location = Coordinate(0, 0, 0)
    self._gripper_width = 0.0
    self._closed = False

  async def pick_up_at_location(
    self,
    location: Coordinate,
    resource_width: float,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    logger.info("pick_up_at_location: %s width=%.1f", location, resource_width)
    self._location = location
    self._gripper_width = resource_width
    self._closed = True
    await asyncio.sleep(self._delay)

  async def drop_at_location(
    self,
    location: Coordinate,
    resource_width: float,
    backend_params: Optional[BackendParams] = None,
  ) -> None:
    logger.info("drop_at_location: %s", location)
    self._location = location
    self._closed = False
    await asyncio.sleep(self._delay)

  async def move_to_location(
    self, location: Coordinate, backend_params: Optional[BackendParams] = None
  ) -> None:
    logger.info("move_to_location: %s", location)
    self._location = location
    await asyncio.sleep(self._delay)

  async def open_gripper(
    self, gripper_width: float, backend_params: Optional[BackendParams] = None
  ) -> None:
    logger.info("open_gripper: %.1f mm", gripper_width)
    self._gripper_width = gripper_width
    self._closed = False

  async def close_gripper(
    self, gripper_width: float, backend_params: Optional[BackendParams] = None
  ) -> None:
    logger.info("close_gripper: %.1f mm", gripper_width)
    self._gripper_width = gripper_width
    self._closed = True

  async def is_gripper_closed(self, backend_params: Optional[BackendParams] = None) -> bool:
    return self._closed

  async def halt(self, backend_params: Optional[BackendParams] = None) -> None:
    logger.info("halt")

  async def park(self, backend_params: Optional[BackendParams] = None) -> None:
    logger.info("park")
    self._location = Coordinate(0, 0, 0)
    await asyncio.sleep(self._delay)

  async def get_gripper_location(
    self, backend_params: Optional[BackendParams] = None
  ) -> GripperLocation:
    return GripperLocation(location=self._location, rotation=Rotation())
