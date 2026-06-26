"""Hardware test 11: 384-Well Plate Positioning.

Validate positioning accuracy with 384-well plates (3.6mm well diameter,
4.5mm pitch). Critical for verifying per-channel X alignment.

With 8 channels at 9mm spacing and 4.5mm well pitch, channels access
every OTHER row. This test uses the first pass (odd rows):
  Channels 1-8 -> wells A1, C1, E1, G1, I1, K1, M1, O1

Known Issue #8: per-channel X alignment drifts at depth. Channels appear
aligned at home Z but show small X offsets as they descend. This is a
mechanical issue with no software fix. 384-well plates (3.6mm opening)
are at risk. This test validates whether the drift is too severe for
384-well work.

================================================================================
OPERATOR SETUP INSTRUCTIONS
================================================================================

PREREQUISITE: Before running this test, you MUST teach the 384-well plate
Z positions using jog_ui.py. The Z values in this script are placeholders.
  1. Run: python keyser-testing/jog_ui.py
  2. Mount 200uL tips
  3. Teach z_start (just above plate top), z_dispense (dispense height),
     and z_max (max depth) for the 384-well plate
  4. Update the Plate_384_Well_SBS() definition in this file with taught values

Equipment needed:
  - 1x MP 3-Position carrier (Tecan P/N 10612604)
  - 2x 384-well plate, SBS standard (e.g., Corning 3820, Greiner 781280)
      Must be skirted or use an adapter to fit MP_3Pos carrier holders
  - 1x DiTi 200uL SBS tip rack — full box

Deck layout:

  Rail 16 — MP_3Pos carrier:
    Position 1 (front):  384-well plate (source) — fill column 1, odd rows only
    Position 2 (middle): 384-well plate (destination) — empty and dry
    Position 3 (rear):   DiTi 200uL SBS tip rack — full, unused

Source plate fill volume:
  - Fill ONLY the odd rows of column 1: A1, C1, E1, G1, I1, K1, M1, O1
  - Fill 50uL/well (384-well max is ~100-120uL depending on manufacturer)
  - 50uL gives enough depth for 20uL aspiration with margin
  - Use a multichannel pipette or fill all 16 rows — the test only accesses
    odd rows, but extra liquid in even rows won't cause problems
  - Use water (not buffer) for initial positioning validation

Destination plate:
  - Must be completely empty and dry
  - After test, odd rows of column 2 should have ~20uL/well

384-well access pattern (this test, first pass only):
  Channel 1 -> A1/A2  (row 1)
  Channel 2 -> C1/C2  (row 3)
  Channel 3 -> E1/E2  (row 5)
  Channel 4 -> G1/G2  (row 7)
  Channel 5 -> I1/I2  (row 9)
  Channel 6 -> K1/K2  (row 11)
  Channel 7 -> M1/M2  (row 13)
  Channel 8 -> O1/O2  (row 15)

Checklist before running:
  [ ] Z positions taught via jog_ui.py and updated in this script
  [ ] Carrier seated firmly on rail 16
  [ ] Source 384-well plate in position 1, filled per instructions above
  [ ] Destination 384-well plate in position 2, empty and dry
  [ ] Tip rack in position 3, full (column 1 tips will be used)
  [ ] EVOware PC USB disconnected
  [ ] pylabrobot PC USB connected

================================================================================

Usage:
  python keyser-testing/test_v1b1_384well.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from labware_library import DiTi_200ul_SBS_LiHa_Air, MP_3Pos_Corrected
from pylabrobot.resources import Coordinate, CrossSectionType, Well
from pylabrobot.resources.tecan.plates import TecanPlate
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.resources.utils import create_ordered_items_2d
from pylabrobot.resources.well import WellBottomType
from pylabrobot.tecan.evo import TecanEVO

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")


# ============== 384-well plate definition (NOT validated — do not add to labware_library yet) ==============


def _384well_volume_from_height(h: float) -> float:
  """Simple cylinder approximation: V = area * h.

  area = pi * r^2 = pi * 1.8^2 = 10.2 mm^2
  """
  if h > 11.5:
    raise ValueError(f"Height {h} exceeds max well depth 11.5mm for 384-well plate")
  return max(10.2 * h, 0)


def _384well_height_from_volume(liquid_volume: float) -> float:
  """Simple cylinder approximation: h = V / area.

  area = pi * r^2 = pi * 1.8^2 = 10.2 mm^2
  """
  if liquid_volume > 117.3:  # 10.2 * 11.5
    raise ValueError(f"Volume {liquid_volume} exceeds max capacity for 384-well plate")
  return max(liquid_volume / 10.2, 0)


def Plate_384_Well_SBS(name: str) -> TecanPlate:
  """384-well plate, SBS standard footprint.

  SBS/SLAS 4-2004 standard:
    Footprint: 127.76 x 85.48mm
    384 wells: 24 columns x 16 rows
    Well pitch: 4.5mm
    Well diameter: 3.6mm
    P1 (A1 center X from left edge): 14.38mm
    P2 (A1 center Y from top edge): 11.24mm

  dx = P1 - well_center_x = 14.38 - 2.25(=4.5/2) = 12.13mm
  dy = P2 - well_center_y = 11.24 - 2.25(=4.5/2) = 8.99mm

  Z positions are PLACEHOLDER values — TODO: teach from hardware.
  """
  return TecanPlate(
    name=name,
    size_x=127.76,
    size_y=85.48,
    size_z=11.5,
    lid=None,
    model="Plate_384_Well_SBS",
    z_start=300.0,     # TODO: teach from hardware
    z_dispense=200.0,  # TODO: teach from hardware
    z_max=100.0,       # TODO: teach from hardware
    area=10.2,         # pi * 1.8^2 for 3.6mm diameter
    ordered_items=create_ordered_items_2d(
      Well,
      num_items_x=24,
      num_items_y=16,
      dx=12.13,   # SBS P1(14.38) - well_center(2.25)
      dy=8.99,    # SBS P2(11.24) - well_center(2.25)
      dz=0.0,
      item_dx=4.5,
      item_dy=4.5,
      size_x=3.6,
      size_y=3.6,
      size_z=11.5,
      bottom_type=WellBottomType.FLAT,
      material_z_thickness=0.0,
      cross_section_type=CrossSectionType.CIRCLE,
      compute_volume_from_height=_384well_volume_from_height,
      compute_height_from_volume=_384well_height_from_volume,
    ),
  )


# 8-channel access pattern for 384-well plates:
# Channels are spaced 9mm apart, wells are 4.5mm apart, so channels
# hit every OTHER row. First pass = odd rows (A, C, E, G, I, K, M, O).
WELLS_COL1_ODD = ["A1", "C1", "E1", "G1", "I1", "K1", "M1", "O1"]
WELLS_COL2_ODD = ["A2", "C2", "E2", "G2", "I2", "K2", "M2", "O2"]

# Tip pickup uses standard 96-format column 1
TIPS_COL1 = ["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1"]


async def main():
  print("=" * 70)
  print("  Test 11: 384-Well Plate Positioning")
  print("  Validate per-channel X alignment with 3.6mm wells")
  print("=" * 70)

  print()
  print("!" * 70)
  print("!  WARNING — Known Issue #8: Per-Channel X Alignment Drift")
  print("!")
  print("!  Channels appear aligned at home Z but show small X offsets as")
  print("!  they descend. This is a MECHANICAL issue with no software fix.")
  print("!  384-well plates (3.6mm opening) are at risk of tip-to-wall")
  print("!  contact. This test validates whether the drift is acceptable")
  print("!  for 384-well work.")
  print("!" * 70)
  print()

  print("384-well access pattern (first pass, odd rows):")
  print("  Column 1 source: A1, C1, E1, G1, I1, K1, M1, O1")
  print("  Column 2 dest:   A2, C2, E2, G2, I2, K2, M2, O2")
  print("  Well diameter: 3.6mm  |  Well pitch: 4.5mm")
  print("  Channel spacing: 9mm  -> every other row")
  print()

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

  source_plate = Plate_384_Well_SBS("source_384")
  dest_plate = Plate_384_Well_SBS("dest_384")
  tip_rack = DiTi_200ul_SBS_LiHa_Air("tips")
  carrier[0] = source_plate
  carrier[1] = dest_plate
  carrier[2] = tip_rack

  print("Deck layout:")
  print("  MP_3Pos carrier: rail 16")
  print(f"    Position 1: {source_plate.name} (384-well, water in column 1)")
  print(f"    Position 2: {dest_plate.name} (384-well, empty)")
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
    # --- Step 1: Pick up 200uL tips from tip rack col 1 ---
    print("\n--- Step 1: Pick Up 200uL Tips ---")
    print(f"  Tips column 1: {TIPS_COL1}")
    input("  Press ENTER to pick up tips...")
    await evo.pip.pick_up_tips(tip_rack.get_items(TIPS_COL1))
    print("  Tips picked up!")

    # --- Step 2: Move to 384-well source plate col 1, visual check ---
    print("\n--- Step 2: Move to Source 384-Well Plate Column 1 ---")
    print(f"  Target wells: {WELLS_COL1_ODD}")
    print("  Well diameter: 3.6mm — tips must center precisely!")
    print()
    print("  >>> VISUAL INSPECTION POINT <<<")
    print("  Watch the tips as they descend into column 1.")
    print("  Check: are all 8 tips centered in their wells?")
    print("  Check: any tips touching well walls?")
    input("  Press ENTER to aspirate 20uL from column 1...")

    # --- Step 3: Aspirate 20uL from col 1 ---
    print("\n--- Step 3: Aspirate 20uL from Column 1 ---")
    await evo.pip.aspirate(
      source_plate.get_items(WELLS_COL1_ODD), vols=[20] * 8
    )
    print("  Aspirated 20uL from 8 wells!")

    print()
    print("  >>> POST-ASPIRATE INSPECTION <<<")
    print("  Did all tips enter wells cleanly?")
    print("  Any signs of tip-to-wall contact (scraping, deflection)?")
    input("  Press ENTER to continue to dispense step...")

    # --- Step 4: Dispense 20uL into col 2 ---
    print("\n--- Step 4: Dispense 20uL into Column 2 ---")
    print(f"  Target wells: {WELLS_COL2_ODD}")
    print("  Column 2 is 4.5mm to the right of column 1.")
    print()
    print("  >>> VISUAL INSPECTION POINT <<<")
    print("  Watch the tips as they descend into column 2.")
    print("  This is the CRITICAL alignment check — X drift at depth")
    print("  may cause tips to contact well walls in 3.6mm openings.")
    input("  Press ENTER to dispense 20uL into column 2...")

    await evo.pip.dispense(
      dest_plate.get_items(WELLS_COL2_ODD), vols=[20] * 8
    )
    print("  Dispensed 20uL into 8 wells!")

    # --- Step 5: Visual alignment check at dispense depth ---
    print()
    print("  >>> POST-DISPENSE INSPECTION <<<")
    print("  Check the destination plate:")
    print("    - Did liquid dispense into the correct wells?")
    print("    - Any liquid on the plate surface (missed wells)?")
    print("    - Any signs of tip deflection during descent?")
    input("  Press ENTER to continue to tip drop...")

    # --- Step 6: Drop tips ---
    print("\n--- Step 6: Drop Tips ---")
    input("  Press ENTER to drop tips...")
    await evo.pip.drop_tips(tip_rack.get_items(TIPS_COL1))
    print("  Tips dropped!")

    # --- Results ---
    print()
    print("=" * 70)
    print("  Test 11 Complete — Record Results")
    print("=" * 70)
    print()
    print("  Answer the following:")
    print("    1. Did all 8 tips enter column 1 wells without wall contact?")
    print("    2. Did all 8 tips enter column 2 wells without wall contact?")
    print("    3. Was liquid deposited in the correct destination wells?")
    print("    4. Which channels (if any) showed visible X drift?")
    print()
    print("  If ALL tips entered cleanly: 384-well work is FEASIBLE.")
    print("  If 1-2 tips scraped: marginal — note which channels.")
    print("  If 3+ tips scraped: 384-well work NOT recommended (Issue #8).")
    print()
    print("*** 384-WELL POSITIONING TEST COMPLETE ***")

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
