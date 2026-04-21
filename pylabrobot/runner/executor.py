"""Protocol execution engine.

Discovers and runs `async def run(device)` in user protocol code.
Captures stdout/stderr and streams to websocket clients.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import traceback
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ExecutionState(str, Enum):
  IDLE = "idle"
  RUNNING = "running"
  COMPLETED = "completed"
  ERROR = "error"
  STOPPED = "stopped"


class ProtocolExecutor:
  """Executes protocol scripts in a background asyncio task."""

  def __init__(self, on_output: Optional[Callable[[str, str], Any]] = None):
    self._state = ExecutionState.IDLE
    self._task: Optional[asyncio.Task] = None
    self._error: Optional[str] = None
    self._on_output = on_output

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

  async def run(self, code: str, device: Any) -> None:
    if self._state == ExecutionState.RUNNING:
      raise RuntimeError("A protocol is already running")

    self._state = ExecutionState.RUNNING
    self._error = None
    self._emit("--- Protocol started ---", "info")

    self._task = asyncio.current_task()

    try:
      namespace: Dict[str, Any] = {}
      exec(compile(code, "<protocol>", "exec"), namespace)

      run_fn = namespace.get("run")
      if run_fn is None:
        raise ValueError("Protocol must define 'async def run(device):'")
      if not asyncio.iscoroutinefunction(run_fn):
        raise ValueError("'run' must be an async function (async def run(device):)")

      stdout_capture = _StreamCapture(lambda line: self._emit(line, "stdout"))
      stderr_capture = _StreamCapture(lambda line: self._emit(line, "stderr"))

      with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
        await run_fn(device)

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
