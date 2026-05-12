"""Hardware test: TecanEVO pipetting 100uL across columns 4, 5, 6.

Picks up tips, aspirates 100uL from source plate, dispenses into
destination plate, and drops tips — repeated for columns 4, 5, and 6.
Uses a fresh column of tips for each transfer.

Deck layout:
  Rail 16: MP_3Pos carrier
    Position 1: Eppendorf plate (source, water in columns 4-6)
    Position 2: Eppendorf plate (destination, empty)
    Position 3: DiTi_200ul_SBS_LiHa tip rack

Usage:
  python keyser-testing/test_v1b1_pipette_200ul_multi_col.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from labware_library import DiTi_200ul_SBS_LiHa_Air, Eppendorf_96_wellplate_250ul_Vb_skirted, MP_3Pos_Corrected
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.tecan.evo import TecanEVO

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"]
COLS = [4, 5, 6]


async def main():
  print("=" * 60)
  print("  TecanEVO Pipetting Test — 200uL tips, 100uL, cols 4-5-6")
  print("=" * 60)

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
  print("  MP_3Pos carrier: rail 16")
  print(f"    Position 1: {source_plate.name} (water in columns 4-6)")
  print(f"    Position 2: {dest_plate.name} (empty)")
  print(f"    Position 3: {tip_rack.name} (DiTi 200uL)")

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
    for col in COLS:
      wells = [f"{row}{col}" for row in ROWS]

      print(f"\n{'=' * 60}")
      print(f"  Column {col}: pick up, aspirate, dispense, drop off")
      print(f"{'=' * 60}")

      print(f"\n  Pick up tips from column {col}...")
      await evo.pip.pick_up_tips(tip_rack.get_items(wells))
      print("  Tips picked up!")

      print(f"\n  Aspirate 100uL from source column {col}...")
      await evo.pip.aspirate(source_plate.get_items(wells), vols=[100] * 8)
      print("  Aspirated!")

      print(f"\n  Dispense 100uL into dest column {col}...")
      await evo.pip.dispense(dest_plate.get_items(wells), vols=[100] * 8)
      print("  Dispensed!")

      print(f"\n  Drop tips back into column {col}...")
      await evo.pip.drop_tips(tip_rack.get_items(wells))
      print("  Tips dropped!")

      print(f"\n  Column {col} transfer complete.")

    print(f"\n{'*' * 60}")
    print("  ALL TRANSFERS COMPLETE — columns 4, 5, 6 done")
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
