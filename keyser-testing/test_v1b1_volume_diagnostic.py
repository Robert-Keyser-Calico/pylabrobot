"""Diagnostic: determine why dispensed volume is 60-70uL instead of 100uL.

Runs 4 tests, each aspirating 100uL from the source plate and dispensing
into a different column of the destination plate so results can be compared
visually (or gravimetrically).

  Col 4 — Baseline:    plain aspirate + dispense (reproduces the problem)
  Col 5 — Blow-out:    dispense with 20uL blow-out air to expel residual
  Col 6 — Pre-wet:     3x mix in source before aspirating (wets tip walls)
  Col 7 — Both:        pre-wet mix + blow-out

Each test picks up fresh tips, so tip seal is consistent.

Deck layout:
  Rail 16: MP_3Pos carrier
    Position 1: Eppendorf plate (source, water in columns 4-7)
    Position 2: Eppendorf plate (destination, empty)
    Position 3: DiTi_200ul_SBS_LiHa tip rack

Usage:
  python keyser-testing/test_v1b1_volume_diagnostic.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from labware_library import DiTi_200ul_SBS_LiHa_Air, Eppendorf_96_wellplate_250ul_Vb_skirted, MP_3Pos_Corrected
from pylabrobot.capabilities.liquid_handling.standard import Mix
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.tecan.evo import TecanEVO

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"]

TESTS = [
  {
    "name": "Baseline",
    "col": 4,
    "tip_col": 1,
    "blow_out": None,
    "mix": None,
  },
  {
    "name": "Blow-out (15uL air)",
    "col": 5,
    "tip_col": 2,
    "blow_out": 15.0,
    "mix": None,
  },
  {
    "name": "Pre-wet (3x mix)",
    "col": 6,
    "tip_col": 3,
    "blow_out": None,
    "mix": Mix(volume=100, repetitions=3, flow_rate=100),
  },
  {
    "name": "Pre-wet + Blow-out",
    "col": 7,
    "tip_col": 4,
    "blow_out": 15.0,
    "mix": Mix(volume=100, repetitions=3, flow_rate=100),
  },
]


async def main():
  print("=" * 60)
  print("  Volume Diagnostic — 200uL tips, 100uL target")
  print("=" * 60)
  print()
  print("  Col 4: Baseline (plain aspirate + dispense)")
  print("  Col 5: Blow-out (15uL air after dispense)")
  print("  Col 6: Pre-wet (3x mix before aspirate)")
  print("  Col 7: Pre-wet + Blow-out (both)")
  print()
  print("  Compare destination columns to identify the cause.")

  deck = EVO150Deck()
  evo = TecanEVO(
    name="evo",
    deck=deck,
    diti_count=8,
    air_liha=True,
    has_roma=True,
    packet_read_timeout=30,
    read_timeout=120,
    write_timeout=120,
  )

  carrier = MP_3Pos_Corrected("carrier")
  deck.assign_child_resource(carrier, rails=16)

  source_plate = Eppendorf_96_wellplate_250ul_Vb_skirted("source")
  dest_plate = Eppendorf_96_wellplate_250ul_Vb_skirted("dest")
  tip_rack = DiTi_200ul_SBS_LiHa_Air("tips")
  carrier[0] = source_plate
  carrier[1] = dest_plate
  carrier[2] = tip_rack

  print("\nDeck layout:")
  print(f"  Position 1: {source_plate.name} (water in cols 4-7)")
  print(f"  Position 2: {dest_plate.name} (empty)")
  print(f"  Position 3: {tip_rack.name}")

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

  try:
    for test in TESTS:
      col = test["col"]
      tip_col = test["tip_col"]
      name = test["name"]
      wells = [f"{row}{col}" for row in ROWS]
      tip_wells = [f"{row}{tip_col}" for row in ROWS]

      print(f"\n{'=' * 60}")
      print(f"  Test: {name} (col {col}, tips from col {tip_col})")
      print(f"{'=' * 60}")

      input(f"\n  Press Enter to start '{name}'...")

      # Pick up tips
      print(f"  Picking up tips from col {tip_col}...")
      await evo.pip.pick_up_tips(tip_rack.get_items(tip_wells))
      print("  Tips mounted.")

      # Aspirate (with optional pre-wet mix)
      asp_kwargs = {}
      if test["mix"] is not None:
        asp_kwargs["mix"] = [test["mix"]] * 8
        print("  Aspirating 100uL with pre-wet mix (3x 100uL)...")
      else:
        print("  Aspirating 100uL...")
      await evo.pip.aspirate(source_plate.get_items(wells), vols=[100] * 8, **asp_kwargs)
      print("  Aspirated.")

      # Dispense (with optional blow-out)
      disp_kwargs = {}
      if test["blow_out"] is not None:
        disp_kwargs["blow_out_air_volume"] = [test["blow_out"]] * 8
        print(f"  Dispensing 100uL with {test['blow_out']}uL blow-out...")
      else:
        print("  Dispensing 100uL...")
      await evo.pip.dispense(dest_plate.get_items(wells), vols=[100] * 8, **disp_kwargs)
      print("  Dispensed.")

      # Drop tips
      print(f"  Dropping tips into col {tip_col}...")
      await evo.pip.drop_tips(tip_rack.get_items(tip_wells))
      print("  Tips dropped.")

      print(f"  '{name}' complete — check dest plate col {col}.")

    print(f"\n{'*' * 60}")
    print("  ALL TESTS COMPLETE")
    print("  Compare dest plate columns 4-7 to identify the cause:")
    print("    Col 4 vs 5: blow-out effect (residual in tip)")
    print("    Col 4 vs 6: pre-wet effect (tip wall wetting)")
    print("    Col 7:      combined effect")
    print(f"{'*' * 60}")

  except Exception as e:
    print(f"\nTest FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

  finally:
    pip_be = evo.pip.backend
    z_range = pip_be._z_range
    num_ch = pip_be.num_channels
    z_params = ",".join([str(z_range)] * num_ch)
    await evo._driver.send_command("C5", command=f"PAZ{z_params}")

    print("\nStopping...")
    await evo.stop()
    print("Done.")


if __name__ == "__main__":
  asyncio.run(main())
