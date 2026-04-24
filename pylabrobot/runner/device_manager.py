"""Device lifecycle manager for the Protocol Runner.

Manages connection to real hardware or simulation, tracks state,
and provides the device instance for protocol execution.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Dict, Optional

from pylabrobot.resources import Resource

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
  DISCONNECTED = "disconnected"
  CONNECTING = "connecting"
  CONNECTED = "connected"
  DISCONNECTING = "disconnecting"
  ERROR = "error"


class DeviceMode(str, Enum):
  SIMULATION = "simulation"
  HARDWARE = "hardware"


class DeviceManager:
  """Manages device lifecycle for simulation and hardware modes.

  The device persists across protocol runs — connect once, run many.
  The deck layout is set from the protocol script's ``deck`` variable.
  """

  def __init__(self):
    self._state = ConnectionState.DISCONNECTED
    self._mode = DeviceMode.SIMULATION
    self._device: Optional[Any] = None
    self._deck: Optional[Resource] = None
    self._error: Optional[str] = None
    self._hardware_config: Dict[str, Any] = {
      "device_type": "TecanEVO",
      "diti_count": 8,
      "air_liha": True,
      "has_roma": True,
      "packet_read_timeout": 30,
      "read_timeout": 120,
      "write_timeout": 120,
    }

  @property
  def state(self) -> ConnectionState:
    return self._state

  @property
  def mode(self) -> DeviceMode:
    return self._mode

  @property
  def device(self) -> Optional[Any]:
    return self._device

  @property
  def deck(self) -> Optional[Resource]:
    return self._deck

  @property
  def error(self) -> Optional[str]:
    return self._error

  @property
  def is_connected(self) -> bool:
    return self._state == ConnectionState.CONNECTED

  def set_deck(self, deck: Resource) -> None:
    self._deck = deck

  def set_hardware_config(self, config: Dict[str, Any]) -> None:
    self._hardware_config.update(config)

  async def connect(self, mode: DeviceMode = DeviceMode.SIMULATION) -> None:
    if self._state == ConnectionState.CONNECTED:
      raise RuntimeError("Already connected")
    if self._state == ConnectionState.CONNECTING:
      raise RuntimeError("Connection in progress")

    self._state = ConnectionState.CONNECTING
    self._mode = mode
    self._error = None

    try:
      if mode == DeviceMode.SIMULATION:
        await self._connect_simulation()
      else:
        await self._connect_hardware()

      self._state = ConnectionState.CONNECTED
      logger.info("Device connected (mode=%s)", mode.value)

    except Exception as e:
      self._state = ConnectionState.ERROR
      self._error = str(e)
      logger.error("Connection failed: %s", e)
      raise

  async def disconnect(self) -> None:
    if self._state not in (ConnectionState.CONNECTED, ConnectionState.ERROR):
      return

    self._state = ConnectionState.DISCONNECTING
    try:
      if self._device is not None:
        await self._device.stop()
    except Exception as e:
      logger.warning("Error during disconnect: %s", e)
    finally:
      self._device = None
      self._state = ConnectionState.DISCONNECTED
      logger.info("Device disconnected")

  async def _connect_simulation(self) -> None:
    if self._deck is None:
      raise ValueError("No deck configured. Run a protocol script first to set up the deck.")

    from pylabrobot.runner.simulation import create_simulated_device

    self._device = create_simulated_device(
      self._deck,
      num_channels=self._hardware_config.get("diti_count", 8),
      has_arm=self._hardware_config.get("has_roma", True),
    )
    await self._device.setup()

  async def _connect_hardware(self) -> None:
    if self._deck is None:
      raise ValueError("No deck configured. Run a protocol script first to set up the deck.")

    cfg = self._hardware_config
    device_type = cfg.get("device_type", "TecanEVO")

    if device_type == "TecanEVO":
      from pylabrobot.tecan.evo import TecanEVO

      self._device = TecanEVO(
        name="evo",
        deck=self._deck,
        diti_count=cfg.get("diti_count", 8),
        air_liha=cfg.get("air_liha", True),
        has_roma=cfg.get("has_roma", True),
        packet_read_timeout=cfg.get("packet_read_timeout", 30),
        read_timeout=cfg.get("read_timeout", 120),
        write_timeout=cfg.get("write_timeout", 120),
      )
      await self._device.setup()
    else:
      raise ValueError(f"Unknown device type: {device_type}")

  def status_dict(self) -> Dict[str, Any]:
    return {
      "state": self._state.value,
      "mode": self._mode.value,
      "error": self._error,
      "device_type": self._hardware_config.get("device_type"),
      "has_device": self._device is not None,
      "has_deck": self._deck is not None,
    }
