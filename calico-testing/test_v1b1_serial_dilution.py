"""Hardware test: TecanEVO v1b1 serial dilution with 200uL tips.

Test 10: Serial Dilution — aspirate from source, dispense into dest column,
then re-aspirate from that dest column and dispense into the next. Tests
multi-step liquid handling accuracy and carryover.

Same tips are used for all 3 transfers (no tip change between transfers).

================================================================================
OPERATOR SETUP INSTRUCTIONS
================================================================================

Equipment needed:
  - 1x MP 3-Position carrier (Tecan P/N 10612604)
  - 1x Eppendorf twin.tec 96-well plate (source, P/N 0030133374) — skirted
  - 1x Eppendorf twin.tec 96-well plate (destination, same P/N) — skirted
  - 1x DiTi 200uL SBS tip rack — full box

Deck layout:

  Rail 16 — MP_3Pos carrier:
    Position 1 (front):  Source plate — fill column 1 (A1-H1) with 200uL water each
    Position 2 (middle): Destination plate — empty and dry
    Position 3 (rear):   DiTi 200uL SBS tip rack — full, unused

Source plate fill volume:
  - Fill 200uL/well in column 1 (A1-H1)
  - The test aspirates 100uL per transfer x 1 transfer from source = 100uL used
  - 200uL fill provides 2x margin for tip immersion depth and LLD reliability
  - Only column 1 needs liquid; columns 2-12 should be empty

Destination plate:
  - Must be completely empty and dry
  - After the test, columns 1, 2, 3 will each contain ~100uL/well
  - Visual check: all 3 columns should have similar fill levels
  - Decreasing volume across columns indicates carryover / residual loss

Checklist before running:
  [ ] Carrier seated firmly on rail 16
  [ ] Source plate in position 1, filled with 200uL water in col 1 (A1-H1)
  [ ] Destination plate in position 2, empty and dry
  [ ] Tip rack in position 3, full (column 1 tips will be used)
  [ ] EVOware PC USB disconnected
  [ ] pylabrobot PC USB connected

================================================================================

Usage:
  python keyser-testing/test_v1b1_serial_dilution.py
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
COLUMN_1 = [f"{row}1" for row in ROWS]
COLUMN_2 = [f"{row}2" for row in ROWS]
COLUMN_3 = [f"{row}3" for row in ROWS]


async def main():
  print("=" * 60)
  print("  TecanEVO v1b1 Serial Dilution Test")
  print("  200uL tips, 100uL volume, 3 transfers")
  print("=" * 60)

  # --- Deck setup ---
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
  print(f"    Position 1: {source_plate.name} (water in column 1)")
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
    input("\nPress Enter to begin serial dilution sequence...")

    # --- Step 1: Pick up tips from column 1 ---
    print("\n--- Step 1: Pick Up 200uL Tips (column 1) ---")
    await evo.pip.pick_up_tips(tip_rack.get_items(COLUMN_1))
    print("  Tips picked up!")

    # --- Step 2: Transfer 1 — source col 1 -> dest col 1 ---
    print("\n--- Step 2: Transfer 1 — source col 1 -> dest col 1 ---")
    print("  Aspirating 100uL from source plate column 1...")
    await evo.pip.aspirate(source_plate.get_items(COLUMN_1), vols=[100] * 8)
    print("  Aspirated!")
    print("  Dispensing 100uL into dest plate column 1...")
    await evo.pip.dispense(dest_plate.get_items(COLUMN_1), vols=[100] * 8)
    print("  Dispensed!")
    print("  Transfer 1 complete.")

    # --- Step 3: Transfer 2 — dest col 1 -> dest col 2 ---
    print("\n--- Step 3: Transfer 2 — dest col 1 -> dest col 2 ---")
    print("  Aspirating 100uL from dest plate column 1...")
    await evo.pip.aspirate(dest_plate.get_items(COLUMN_1), vols=[100] * 8)
    print("  Aspirated!")
    print("  Dispensing 100uL into dest plate column 2...")
    await evo.pip.dispense(dest_plate.get_items(COLUMN_2), vols=[100] * 8)
    print("  Dispensed!")
    print("  Transfer 2 complete.")

    # --- Step 4: Transfer 3 — dest col 2 -> dest col 3 ---
    print("\n--- Step 4: Transfer 3 — dest col 2 -> dest col 3 ---")
    print("  Aspirating 100uL from dest plate column 2...")
    await evo.pip.aspirate(dest_plate.get_items(COLUMN_2), vols=[100] * 8)
    print("  Aspirated!")
    print("  Dispensing 100uL into dest plate column 3...")
    await evo.pip.dispense(dest_plate.get_items(COLUMN_3), vols=[100] * 8)
    print("  Dispensed!")
    print("  Transfer 3 complete.")

    # --- Step 5: Drop tips into column 1 ---
    print("\n--- Step 5: Drop Tips (column 1) ---")
    await evo.pip.drop_tips(tip_rack.get_items(COLUMN_1))
    print("  Tips dropped!")

    print("\n*** SERIAL DILUTION TEST PASSED ***")

  except Exception as e:
    print(f"\nTest FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

  finally:
    pip_be = evo.pip.backend
    z_range = pip_be._z_range
    num_ch = pip_be.num_channels
    z_params = ",".join([str(z_range)] * num_ch)
    await evo.driver.send_command("C5", command=f"PAZ{z_params}")

    print("\nStopping...")
    await evo.stop()
    print("Done.")


if __name__ == "__main__":
  asyncio.run(main())
