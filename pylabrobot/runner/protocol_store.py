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
"""Pipetting Protocol — 200uL tips, 100uL transfer

Deck layout:
  Rail 16: MP_3Pos carrier
    Position 1: source plate (water in column 2)
    Position 2: destination plate (empty)
    Position 3: DiTi 200uL tip rack
"""

# === Imports ===
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.resources.tecan.plate_carriers import MP_3Pos
from pylabrobot.resources.tecan.tip_racks import DiTi_200ul_SBS_LiHa
from pylabrobot.resources.eppendorf.plates import Eppendorf_96_wellplate_250ul_Vb

# === Deck Setup ===
deck = EVO150Deck()

carrier = MP_3Pos("carrier")
deck.assign_child_resource(carrier, rails=16)
carrier[0] = Eppendorf_96_wellplate_250ul_Vb("source")
carrier[1] = Eppendorf_96_wellplate_250ul_Vb("dest")
carrier[2] = DiTi_200ul_SBS_LiHa("tips")

# === Protocol ===
COLUMN_2 = ["A2", "B2", "C2", "D2", "E2", "F2", "G2", "H2"]


async def run(device):
  tips = deck.get_resource("tips")
  source = deck.get_resource("source")
  dest = deck.get_resource("dest")

  print("Picking up 200uL tips from column 2...")
  await device.pip.pick_up_tips(tips.get_items(COLUMN_2))

  print("Aspirating 100 uL from source column 2...")
  await device.pip.aspirate(source.get_items(COLUMN_2), vols=[100] * 8)

  print("Dispensing 100 uL to dest column 2...")
  await device.pip.dispense(dest.get_items(COLUMN_2), vols=[100] * 8)

  print("Dropping tips...")
  await device.pip.drop_tips(tips.get_items(COLUMN_2))

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
