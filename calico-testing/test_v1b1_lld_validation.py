"""Test 12: Liquid Level Detection (LLD) Validation.

Tests LLD at 4 fill levels in a 96-well plate to verify detection
accuracy and reliability.

Fill levels (pre-filled by operator before running):
  Col 1: Full   (~200uL/well)
  Col 2: Half   (~100uL/well)
  Col 3: Low    (~25uL/well)
  Col 4: Empty  (air) — should fail/timeout, verify graceful error handling

For each fill level:
  1. Pick up fresh 200uL tips (from tip rack cols 1-4)
  2. Aspirate 10uL with LLD enabled
  3. Read detected Z positions via RVZ
  4. Dispense into destination plate
  5. Drop tips

================================================================================
OPERATOR SETUP INSTRUCTIONS
================================================================================

Equipment needed:
  - 1x MP 3-Position carrier (Tecan P/N 10612604)
  - 1x Eppendorf twin.tec 96-well plate (source, P/N 0030133374) — skirted
  - 1x Eppendorf twin.tec 96-well plate (destination, same P/N) — skirted
  - 1x DiTi 200uL SBS tip rack — full box (columns 1-4 will be used)
  - Multichannel pipette for plate filling

Deck layout:

  Rail 16 — MP_3Pos carrier:
    Position 1 (front):  Source plate — pre-filled per instructions below
    Position 2 (middle): Destination plate — empty and dry
    Position 3 (rear):   DiTi 200uL SBS tip rack — full, unused

Source plate fill instructions (use multichannel pipette, water only):

  Column 1 — FULL:   fill A1-H1 with 200uL water each
    Expected liquid height: ~18mm from well bottom
    This is near the plate top — LLD should detect immediately

  Column 2 — HALF:   fill A2-H2 with 100uL water each
    Expected liquid height: ~10mm from well bottom
    LLD should detect at roughly half the well depth

  Column 3 — LOW:    fill A3-H3 with 25uL water each
    Expected liquid height: ~3mm from well bottom
    This is the challenging case — small meniscus, low signal

  Column 4 — EMPTY:  leave A4-H4 completely empty and dry
    No liquid — LLD should fail/timeout (this is expected behavior)
    Make sure wells are DRY (no residual droplets from handling)

  All other columns (5-12): leave empty, not used

Destination plate:
  - Must be completely empty and dry
  - Used to dispense the 10uL aspirated during each LLD test
  - After test, columns 1-3 will each have ~10uL/well

Tip rack:
  - Must be full — the test uses columns 1-4 (fresh tips for each fill level)
  - Column 1 tips: used for Full test
  - Column 2 tips: used for Half test
  - Column 3 tips: used for Low test
  - Column 4 tips: used for Empty test

Checklist before running:
  [ ] Carrier seated firmly on rail 16
  [ ] Source plate in position 1, filled per column instructions above
  [ ] Column 4 of source plate is EMPTY and DRY
  [ ] Destination plate in position 2, empty and dry
  [ ] Tip rack in position 3, full (columns 1-4 will be used)
  [ ] EVOware PC USB disconnected
  [ ] pylabrobot PC USB connected

================================================================================

Usage:
  python keyser-testing/test_v1b1_lld_validation.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from labware_library import DiTi_200ul_SBS_LiHa_Air, Eppendorf_96_wellplate_250ul_Vb_skirted, MP_3Pos_Corrected
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.tecan.evo import TecanEVO
from pylabrobot.tecan.evo.params import TecanPIPParams

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

# Enable DEBUG logging for tecan modules to capture raw LLD Z values
logging.getLogger("pylabrobot.tecan").setLevel(logging.DEBUG)

ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"]

FILL_LEVELS = [
  {"label": "Full (~200uL)",  "src_col": 1, "tip_col": 1, "fill_vol": 200, "expect_fail": False},
  {"label": "Half (~100uL)",  "src_col": 2, "tip_col": 2, "fill_vol": 100, "expect_fail": False},
  {"label": "Low (~25uL)",    "src_col": 3, "tip_col": 3, "fill_vol": 25,  "expect_fail": False},
  {"label": "Empty (air)",    "src_col": 4, "tip_col": 4, "fill_vol": 0,   "expect_fail": True},
]

ASPIRATE_VOL = 10


def compute_expected_z_height(fill_vol: float) -> float:
  from labware_library import _compute_height_from_volume
  if fill_vol <= 0:
    return 0.0
  return _compute_height_from_volume(fill_vol)


async def main():
  print("=" * 60)
  print("  Test 12: LLD Validation — 4 Fill Levels")
  print("=" * 60)
  print()
  print("  Fill levels:")
  for fl in FILL_LEVELS:
    expected_h = compute_expected_z_height(fl["fill_vol"])
    fail_note = " (expect LLD failure)" if fl["expect_fail"] else ""
    print(f"    Col {fl['src_col']}: {fl['label']:20s}  expected height: {expected_h:.1f}mm{fail_note}")
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

  carrier = MP_3Pos_Corrected("carrier")
  deck.assign_child_resource(carrier, rails=16)

  source_plate = Eppendorf_96_wellplate_250ul_Vb_skirted("source")
  dest_plate = Eppendorf_96_wellplate_250ul_Vb_skirted("dest")
  tip_rack = DiTi_200ul_SBS_LiHa_Air("tips")
  carrier[0] = source_plate
  carrier[1] = dest_plate
  carrier[2] = tip_rack

  print("Deck layout:")
  print("  MP_3Pos carrier: rail 16")
  print(f"    Position 0: {source_plate.name} (cols 1-3 pre-filled, col 4 empty)")
  print(f"    Position 1: {dest_plate.name} (empty)")
  print(f"    Position 2: {tip_rack.name} (DiTi 200uL)")

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

  lld_params = TecanPIPParams(liquid_detection_proc=7, liquid_detection_sense=1)

  pip_be = evo.pip.backend
  liha = pip_be.liha

  results = []

  try:
    for fl in FILL_LEVELS:
      label = fl["label"]
      src_col = fl["src_col"]
      tip_col = fl["tip_col"]
      fill_vol = fl["fill_vol"]
      expect_fail = fl["expect_fail"]

      src_wells = [f"{row}{src_col}" for row in ROWS]
      tip_wells = [f"{row}{tip_col}" for row in ROWS]

      expected_h = compute_expected_z_height(fill_vol)

      print(f"\n{'=' * 60}")
      print(f"  Fill level: {label}")
      print(f"  Source col {src_col}, Tips col {tip_col}")
      print(f"  Expected liquid height: {expected_h:.1f}mm")
      if expect_fail:
        print("  ** Expecting LLD failure (empty well) **")
      print(f"{'=' * 60}")

      input(f"\n  Press Enter to start {label} test...")

      print(f"\n  Pick up tips from col {tip_col}...")
      await evo.pip.pick_up_tips(tip_rack.get_items(tip_wells))
      print("  Tips picked up!")

      z_values = None
      lld_failed = False

      if expect_fail:
        print(f"\n  Aspirate {ASPIRATE_VOL}uL from source col {src_col} (LLD enabled)...")
        print("  (Expecting LLD failure on empty wells...)")
        try:
          await evo.pip.aspirate(
            source_plate.get_items(src_wells),
            vols=[ASPIRATE_VOL] * 8,
            backend_params=lld_params,
          )
          print("  WARNING: LLD did NOT fail on empty wells (unexpected)")
          try:
            z_values = await liha.read_z_after_liquid_detection()
            print(f"  Detected Z values: {z_values}")
          except Exception as rz_err:
            print(f"  Could not read Z values: {rz_err}")

          results.append({
            "label": label,
            "z_values": z_values,
            "expected_h": expected_h,
            "status": "UNEXPECTED PASS (LLD should have failed)",
          })
        except Exception as e:
          lld_failed = True
          print(f"  LLD failure (EXPECTED): {type(e).__name__}: {e}")
          results.append({
            "label": label,
            "z_values": None,
            "expected_h": expected_h,
            "status": f"EXPECTED FAIL: {type(e).__name__}",
          })
      else:
        print(f"\n  Aspirate {ASPIRATE_VOL}uL from source col {src_col} (LLD enabled)...")
        try:
          await evo.pip.aspirate(
            source_plate.get_items(src_wells),
            vols=[ASPIRATE_VOL] * 8,
            backend_params=lld_params,
          )
          print("  Aspirated!")

          try:
            z_values = await liha.read_z_after_liquid_detection()
            print(f"  Detected Z values (1/10 mm): {z_values}")
          except Exception as rz_err:
            print(f"  Could not read Z values: {rz_err}")

          results.append({
            "label": label,
            "z_values": z_values,
            "expected_h": expected_h,
            "status": "PASSED",
          })
        except Exception as e:
          print(f"  LLD FAILED (unexpected): {type(e).__name__}: {e}")
          import traceback
          traceback.print_exc()
          results.append({
            "label": label,
            "z_values": None,
            "expected_h": expected_h,
            "status": f"FAILED: {type(e).__name__}: {e}",
          })
          lld_failed = True

      if not lld_failed:
        dest_wells = [f"{row}{src_col}" for row in ROWS]
        print(f"\n  Dispense {ASPIRATE_VOL}uL into dest col {src_col}...")
        await evo.pip.dispense(
          dest_plate.get_items(dest_wells),
          vols=[ASPIRATE_VOL] * 8,
        )
        print("  Dispensed!")

      print(f"\n  Drop tips into col {tip_col}...")
      await evo.pip.drop_tips(tip_rack.get_items(tip_wells))
      print("  Tips dropped!")

      print(f"\n  {label} test complete.")

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

  print(f"\n{'*' * 70}")
  print("  LLD VALIDATION RESULTS")
  print(f"{'*' * 70}")
  print(f"  {'Fill Level':<22s} {'Expected H':>10s} {'Status'}")
  print(f"  {'-' * 22} {'-' * 10} {'-' * 30}")

  for r in results:
    expected_str = f"{r['expected_h']:.1f}mm" if r["expected_h"] > 0 else "N/A"
    print(f"  {r['label']:<22s} {expected_str:>10s} {r['status']}")

    if r["z_values"] is not None:
      print(f"  {'':22s} Detected Z (1/10 mm) per channel:")
      for ch_idx, z_val in enumerate(r["z_values"]):
        if z_val != 0:
          z_mm = z_val / 10.0
          print(f"  {'':22s}   Ch {ch_idx}: Z={z_val} ({z_mm:.1f}mm)")

  print(f"{'*' * 70}")


if __name__ == "__main__":
  asyncio.run(main())
