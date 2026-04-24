"""Protocol execution engine.

Executes notebook-style scripts that define a deck layout and a
run(device) function. Supports two modes:

- **Standalone**: The executor creates a simulated device from the script's
  deck variable, runs the protocol, then tears down.
- **Managed**: A DeviceManager provides a persistent device (real or simulated).
  The script's deck is used to configure the manager, then run() is called
  with the managed device.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import traceback
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ExecutionState(str, Enum):
  IDLE = "idle"
  RUNNING = "running"
  COMPLETED = "completed"
  ERROR = "error"
  STOPPED = "stopped"


class ProtocolExecutor:
  """Executes notebook-style protocol scripts."""

  def __init__(
    self,
    on_output: Optional[Callable[[str, str], Any]] = None,
    on_deck_ready: Optional[Callable[[Any, Any], Any]] = None,
  ):
    self._state = ExecutionState.IDLE
    self._task: Optional[asyncio.Task] = None
    self._error: Optional[str] = None
    self._on_output = on_output
    self._on_deck_ready = on_deck_ready
    self._device: Optional[Any] = None

  @property
  def state(self) -> ExecutionState:
    return self._state

  @property
  def error(self) -> Optional[str]:
    return self._error

  def _emit(self, text: str, stream: str = "stdout") -> None:
    if self._on_output:
      try:
        self._on_output(text, stream)
      except Exception:
        pass

  async def run(self, code: str, device: Optional[Any] = None) -> None:
    """Execute a notebook-style protocol script.

    Args:
      code: Protocol source code. Must define a ``deck`` variable and
            ``async def run(device):``.
      device: If provided, use this device instead of creating a simulated one.
              The device must already be set up. Used by DeviceManager for
              hardware mode.
    """
    if self._state == ExecutionState.RUNNING:
      raise RuntimeError("A protocol is already running")

    self._state = ExecutionState.RUNNING
    self._error = None
    self._device = None
    managed_device = device is not None
    self._emit("--- Executing script ---", "info")

    self._task = asyncio.current_task()

    try:
      namespace: Dict[str, Any] = {}

      stdout_capture = _StreamCapture(lambda line: self._emit(line, "stdout"))
      stderr_capture = _StreamCapture(lambda line: self._emit(line, "stderr"))

      with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
        exec(compile(code, "<protocol>", "exec"), namespace)

      from pylabrobot.resources.deck import Deck

      deck = None
      for val in namespace.values():
        if isinstance(val, Deck):
          deck = val
          break

      if deck is None:
        raise ValueError(
          "Script must create a Deck variable.\n"
          "Example: deck = EVO150Deck()"
        )

      run_fn = namespace.get("run")
      if run_fn is None:
        raise ValueError(
          "Script must define 'async def run(device):'.\n"
          "This function receives the device."
        )
      if not asyncio.iscoroutinefunction(run_fn):
        raise ValueError("'run' must be an async function (async def run(device):)")

      if device is None:
        self._emit("Deck configured, setting up simulated device...", "info")
        from pylabrobot.runner.simulation import create_simulated_device

        device = create_simulated_device(deck, num_channels=8, has_arm=True)
        await device.setup()
        self._device = device

      if self._on_deck_ready:
        self._on_deck_ready(deck, device)

      self._emit("Device ready, running protocol...", "info")

      with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
        await run_fn(device)

      stdout_capture.flush()
      stderr_capture.flush()

      self._state = ExecutionState.COMPLETED
      self._emit("--- Protocol completed ---", "info")

    except asyncio.CancelledError:
      self._state = ExecutionState.STOPPED
      self._emit("--- Protocol stopped ---", "info")

    except Exception as e:
      self._state = ExecutionState.ERROR
      self._error = str(e)
      tb = traceback.format_exc()
      self._emit(tb, "stderr")
      self._emit(f"--- Protocol error: {e} ---", "stderr")

    finally:
      if self._device is not None and not managed_device:
        try:
          await self._device.stop()
        except Exception:
          pass
      self._task = None

  def stop(self) -> None:
    if self._task is not None and not self._task.done():
      self._task.cancel()


class _StreamCapture(io.TextIOBase):
  """Captures writes to stdout/stderr and forwards each line to a callback."""

  def __init__(self, callback: Callable[[str], None]):
    self._callback = callback
    self._buffer = ""

  def write(self, s: str) -> int:
    self._buffer += s
    while "\n" in self._buffer:
      line, self._buffer = self._buffer.split("\n", 1)
      self._callback(line)
    return len(s)

  def flush(self) -> None:
    if self._buffer:
      self._callback(self._buffer)
      self._buffer = ""
