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
"""My Protocol

The run() function receives the device (simulated or real).
Access deck resources by name via the resource tree.
"""


async def run(device):
  deck = device.children[0]
  tips = deck.get_resource("tips_1")
  source = deck.get_resource("source_plate")
  dest = deck.get_resource("dest_plate")

  # Pick up tips from column 1
  tip_spots = tips.get_items(["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1"])
  print(f"Picking up tips from {tips.name}...")
  await device.pip.pick_up_tips(tip_spots)

  # Aspirate from source
  wells_src = source.get_items(["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1"])
  print("Aspirating 50 uL from source...")
  await device.pip.aspirate(wells_src, vols=[50] * 8)

  # Dispense to dest
  wells_dst = dest.get_items(["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1"])
  print("Dispensing 50 uL to dest...")
  await device.pip.dispense(wells_dst, vols=[50] * 8)

  # Drop tips
  print("Dropping tips...")
  await device.pip.drop_tips(tip_spots)

  print("Protocol complete!")
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
