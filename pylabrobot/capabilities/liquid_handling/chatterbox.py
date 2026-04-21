"""Chatterbox backend for PIP (independent-channel liquid handling).

Logs operations without requiring hardware. Tip tracking and volume
tracking happen at the Capability level, so simulation gets full
state tracking automatically.
"""

import asyncio
import logging
from typing import List, Optional

from pylabrobot.capabilities.capability import BackendParams

from .pip_backend import PIPBackend
from .standard import Aspiration, Dispense, Pickup, TipDrop

logger = logging.getLogger(__name__)


class PIPChatterboxBackend(PIPBackend):
  """No-op PIP backend for simulation and testing."""

  def __init__(self, num_channels: int = 8, delay: float = 0.2):
    self._num_channels = num_channels
    self._delay = delay

  @property
  def num_channels(self) -> int:
    return self._num_channels

  async def pick_up_tips(
    self,
    ops: List[Pickup],
    use_channels: List[int],
    backend_params: Optional[BackendParams] = None,
  ):
    wells = [op.resource.name for op in ops]
    logger.info("pick_up_tips: channels=%s from %s", use_channels, wells)
    await asyncio.sleep(self._delay)

  async def drop_tips(
    self,
    ops: List[TipDrop],
    use_channels: List[int],
    backend_params: Optional[BackendParams] = None,
  ):
    targets = [op.resource.name for op in ops]
    logger.info("drop_tips: channels=%s to %s", use_channels, targets)
    await asyncio.sleep(self._delay)

  async def aspirate(
    self,
    ops: List[Aspiration],
    use_channels: List[int],
    backend_params: Optional[BackendParams] = None,
  ):
    vols = [op.volume for op in ops]
    wells = [op.resource.name for op in ops]
    logger.info("aspirate: %s uL from %s", vols, wells)
    await asyncio.sleep(self._delay)

  async def dispense(
    self,
    ops: List[Dispense],
    use_channels: List[int],
    backend_params: Optional[BackendParams] = None,
  ):
    vols = [op.volume for op in ops]
    wells = [op.resource.name for op in ops]
    logger.info("dispense: %s uL to %s", vols, wells)
    await asyncio.sleep(self._delay)
