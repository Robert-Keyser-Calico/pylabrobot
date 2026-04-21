"""Protocol storage — save/load protocol scripts from disk."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PROTOCOLS_DIR = Path.home() / ".pylabrobot" / "protocols"

STARTER_TEMPLATE = '''\
"""My Protocol"""


async def run(evo):
  # Deck resources are available via the resource tree:
  #   deck = evo.children[0]
  #   plate = deck.get_resource("source_plate")
  #   tips = deck.get_resource("tips_1")

  print("Hello from PyLabRobot!")
'''


@dataclass
class ProtocolMeta:
  name: str
  description: str = ""
  created: str = ""
  modified: str = ""


class ProtocolStore:
  def __init__(self, directory: Optional[Path] = None):
    self._dir = directory or PROTOCOLS_DIR
    self._dir.mkdir(parents=True, exist_ok=True)

  def _py_path(self, name: str) -> Path:
    return self._dir / f"{name}.py"

  def _meta_path(self, name: str) -> Path:
    return self._dir / f"{name}.meta.json"

  def list_protocols(self) -> List[str]:
    return sorted(
      p.stem for p in self._dir.glob("*.py")
      if not p.stem.startswith("_")
    )

  def load(self, name: str) -> str:
    path = self._py_path(name)
    if not path.exists():
      raise FileNotFoundError(f"Protocol '{name}' not found")
    return path.read_text(encoding="utf-8")

  def save(self, name: str, code: str) -> None:
    from datetime import datetime, timezone

    path = self._py_path(name)
    path.write_text(code, encoding="utf-8")

    meta_path = self._meta_path(name)
    now = datetime.now(timezone.utc).isoformat()
    if meta_path.exists():
      meta = json.loads(meta_path.read_text(encoding="utf-8"))
      meta["modified"] = now
    else:
      meta = {"name": name, "description": "", "created": now, "modified": now}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

  def delete(self, name: str) -> None:
    self._py_path(name).unlink(missing_ok=True)
    self._meta_path(name).unlink(missing_ok=True)

  def exists(self, name: str) -> bool:
    return self._py_path(name).exists()
