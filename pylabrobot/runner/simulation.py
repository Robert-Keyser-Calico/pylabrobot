"""Simulated device factory for the Protocol Runner.

Creates device instances with chatterbox backends so protocols can
run without hardware. The resource tree is real — tip tracking,
volume tracking, and plate movements all work normally.
"""

from __future__ import annotations

import logging
from typing import Optional

from pylabrobot.arms.arm import GripperArm
from pylabrobot.arms.chatterbox import GripperArmChatterboxBackend
from pylabrobot.capabilities.liquid_handling.chatterbox import PIPChatterboxBackend
from pylabrobot.capabilities.liquid_handling.pip import PIP
from pylabrobot.device import Device, Driver
from pylabrobot.resources import Coordinate, Resource

logger = logging.getLogger(__name__)


class ChatterboxDriver(Driver):
  """No-op driver for simulation."""

  async def setup(self):
    logger.info("ChatterboxDriver: setup (no hardware)")

  async def stop(self):
    logger.info("ChatterboxDriver: stop")


class SimulatedDevice(Resource, Device):
  """A simulated device with PIP and optional GripperArm capabilities.

  Uses chatterbox backends so all operations log but don't touch hardware.
  The resource tree updates normally (tip tracking, plate moves, volumes).

  Usage::

    deck = build_my_deck()
    sim = create_simulated_device(deck, num_channels=8, has_arm=True)
    await sim.setup()

    # Protocols use sim.pip and sim.arm just like real hardware
    await sim.pip.pick_up_tips(...)
    await sim.arm.move_resource(plate, carrier[0])

    await sim.stop()
  """

  def __init__(
    self,
    deck: Resource,
    num_channels: int = 8,
    has_arm: bool = True,
    name: str = "simulated_device",
  ):
    driver = ChatterboxDriver()
    Resource.__init__(self, name=name, size_x=1315, size_y=780, size_z=765)
    Device.__init__(self, driver=driver)

    self.assign_child_resource(deck, location=Coordinate.zero())

    pip_backend = PIPChatterboxBackend(num_channels=num_channels)
    self.pip = PIP(backend=pip_backend)

    self.arm: Optional[GripperArm] = None
    if has_arm:
      arm_backend = GripperArmChatterboxBackend()
      self.arm = GripperArm(backend=arm_backend, reference_resource=deck)

    caps: list = [self.pip]
    if self.arm is not None:
      caps.append(self.arm)
    self._capabilities = caps


def create_simulated_device(
  deck: Resource,
  num_channels: int = 8,
  has_arm: bool = True,
) -> SimulatedDevice:
  """Factory for creating a simulated device with a given deck layout."""
  return SimulatedDevice(deck=deck, num_channels=num_channels, has_arm=has_arm)
