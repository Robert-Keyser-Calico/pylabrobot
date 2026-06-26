"""Test 9: Multi-tip-size cycle.

Runs the same pipetting workflow (pick up, aspirate, dispense, drop) with
all three tip sizes to validate end-to-end accuracy across the full range.
All three tip racks and plates are set up simultaneously — no swapping.

  Rail  4: MP_3Pos — 50uL tips,   source plate, dest plate  (25uL,  col 1)
  Rail 16: MP_3Pos — 200uL tips,  source plate, dest plate  (100uL, col 1)
  Rail 26: MP_3Pos — 1000uL tips, deep-well source, deep-well dest (500uL, col 1)

Each carrier position:
  Position 1: source plate (water in column 1)
  Position 2: destination plate (empty)
  Position 3: tip rack

================================================================================
OPERATOR SETUP INSTRUCTIONS
================================================================================

Equipment needed:
  - 3x MP 3-Position carriers (Tecan P/N 10612604)
  - 2x Eppendorf twin.tec 96-well plates (source, P/N 0030133374) — skirted
  - 2x Eppendorf twin.tec 96-well plates (destination, same P/N) — skirted
  - 1x 96-well round deep-well plate (source, ~2mL/well) — skirted
  - 1x 96-well round deep-well plate (destination, same type) — skirted
  - 1x DiTi 50uL SBS tip rack (Tecan P/N 30057813) — full box
  - 1x DiTi 200uL SBS tip rack — full box
  - 1x DiTi 1000uL SBS tip rack — full box

Deck layout (front-to-back positions on each carrier):

  Rail 4 — 50uL test:
    Position 1 (front):  Source plate — fill column 1 (A1-H1) with 50uL water each
    Position 2 (middle): Destination plate — empty
    Position 3 (rear):   DiTi 50uL SBS tip rack — full, unused

  Rail 16 — 200uL test:
    Position 1 (front):  Source plate — fill column 1 (A1-H1) with 200uL water each
    Position 2 (middle): Destination plate — empty
    Position 3 (rear):   DiTi 200uL SBS tip rack — full, unused

  Rail 26 — 1000uL test (DEEP-WELL PLATES):
    Position 1 (front):  Deep-well source plate — fill column 1 (A1-H1) with 1000uL water each
    Position 2 (middle): Deep-well destination plate — empty
    Position 3 (rear):   DiTi 1000uL SBS tip rack — full, unused

PREREQUISITE for Rail 26: The deep-well plate Z positions must be taught
  via jog_ui.py before running. Update z_start, z_dispense, z_max in
  labware_library.py -> DeepWell_96_Round_Corrected() with taught values.

Source plate fill volumes:
  - 50uL tips:   fill 50uL/well (2x the 25uL aspirate volume, gives margin)
  - 200uL tips:  fill 200uL/well (2x the 100uL aspirate volume)
  - 1000uL tips: fill 1000uL/well in deep-well plate (2x the 500uL aspirate volume)

Checklist before running:
  [ ] All 3 carriers seated firmly on rails 4, 16, 26
  [ ] All plates pushed fully into carrier positions (click into holders)
  [ ] Source plates filled in column 1 ONLY (A1-H1) with correct volumes
  [ ] Destination plates are empty and dry
  [ ] Tip racks are full (no missing tips in column 1)
  [ ] EVOware PC USB disconnected
  [ ] pylabrobot PC USB connected

================================================================================

Usage:
  python keyser-testing/test_v1b1_multi_tip_cycle.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from labware_library import (
  DeepWell_96_Round_Corrected,
  DiTi_50ul_SBS_LiHa_Air,
  DiTi_200ul_SBS_LiHa_Air,
  DiTi_1000ul_SBS_LiHa_Air,
  Eppendorf_96_wellplate_250ul_Vb_skirted,
  MP_3Pos_Corrected,
)
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.tecan.evo import TecanEVO

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"]
COL = 1
WELLS = [f"{row}{COL}" for row in ROWS]

TIP_TESTS = [
  {"label": "DiTi 50uL",   "rack_fn": DiTi_50ul_SBS_LiHa_Air,   "volume": 25,  "rail": 4,  "plate_fn": Eppendorf_96_wellplate_250ul_Vb_skirted},
  {"label": "DiTi 200uL",  "rack_fn": DiTi_200ul_SBS_LiHa_Air,  "volume": 100, "rail": 16, "plate_fn": Eppendorf_96_wellplate_250ul_Vb_skirted},
  {"label": "DiTi 1000uL", "rack_fn": DiTi_1000ul_SBS_LiHa_Air, "volume": 500, "rail": 26, "plate_fn": DeepWell_96_Round_Corrected},
]


async def main():
  print("=" * 60)
  print("  Test 9: Multi-Tip-Size Cycle")
  print("=" * 60)
  print()
  for t in TIP_TESTS:
    print(f"  Rail {t['rail']:2d}: {t['label']:15s} -> {t['volume']}uL")
  print()

  deck = EVO150Deck()
  evo = TecanEVO(
    name="evo",
    deck=deck,
    diti_count=8,
    air_liha=True,
    has_roma=False,
    packet_read_timeout=30,
    read_timeout=120,
    write_timeout=120,
  )

  carriers = {}
  source_plates = {}
  dest_plates = {}
  tip_racks = {}

  for test in TIP_TESTS:
    rail = test["rail"]
    label = test["label"]
    carrier = MP_3Pos_Corrected(f"carrier_r{rail}")
    deck.assign_child_resource(carrier, rails=rail)
    carriers[rail] = carrier

    plate_fn = test["plate_fn"]
    source = plate_fn(f"source_r{rail}")
    dest = plate_fn(f"dest_r{rail}")
    tips = test["rack_fn"](f"tips_r{rail}")
    carrier[0] = source
    carrier[1] = dest
    carrier[2] = tips
    source_plates[rail] = source
    dest_plates[rail] = dest
    tip_racks[rail] = tips

    print(f"  Rail {rail}: {label}")
    print(f"    Pos 1: {source.name}  Pos 2: {dest.name}  Pos 3: {tips.name}")

  print("\nInitializing...")
  try:
    await evo.setup()
    print(f"  Channels: {evo.pip.num_channels}")
    print("Ready!")
  except Exception as e:
    print(f"Init FAILED: {e}")
    import traceback
    traceback.print_exc()
    return

  results = []

  try:
    for test in TIP_TESTS:
      rail = test["rail"]
      label = test["label"]
      volume = test["volume"]
      tip_rack = tip_racks[rail]
      source = source_plates[rail]
      dest = dest_plates[rail]

      print(f"\n{'=' * 60}")
      print(f"  {label} — {volume}uL — rail {rail}, col {COL}")
      print(f"{'=' * 60}")
      print(f"  Tip rack: {tip_rack.model}")
      print(f"    z_start={tip_rack.z_start}  z_max={tip_rack.z_max}")

      print(f"\n  Starting {label} cycle...")
      await asyncio.sleep(2)

      print(f"\n  Pick up tips from col {COL}...")
      await evo.pip.pick_up_tips(tip_rack.get_items(WELLS))
      print("  Tips picked up!")

      print(f"\n  Aspirate {volume}uL from source col {COL}...")
      await evo.pip.aspirate(source.get_items(WELLS), vols=[volume] * 8)
      print("  Aspirated!")

      print(f"\n  Dispense {volume}uL into dest col {COL}...")
      await evo.pip.dispense(dest.get_items(WELLS), vols=[volume] * 8)
      print("  Dispensed!")

      print(f"\n  Drop tips into col {COL}...")
      await evo.pip.drop_tips(tip_rack.get_items(WELLS))
      print("  Tips dropped!")

      results.append((label, volume, "PASSED"))
      print(f"\n  {label} cycle PASSED — check dest plate on rail {rail}.")

  except Exception as e:
    print(f"\n  FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    label = test["label"]
    volume = test["volume"]
    results.append((label, volume, f"FAILED: {e}"))

  finally:
    pip_be = evo.pip.backend
    z_range = pip_be._z_range
    num_ch = pip_be.num_channels
    z_params = ",".join([str(z_range)] * num_ch)
    await evo.driver.send_command("C5", command=f"PAZ{z_params}")

    print("\nStopping...")
    await evo.stop()
    print("Done.")

  print(f"\n{'*' * 60}")
  print("  RESULTS")
  print(f"{'*' * 60}")
  for label, volume, result in results:
    print(f"  {label:15s}  {volume:4d}uL  {result}")
  print(f"{'*' * 60}")


if __name__ == "__main__":
  asyncio.run(main())
