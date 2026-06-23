"""Quick test: 1000uL tips, 200uL volume.

Validates the zadd tracking fix for larger volumes in small wells.

Deck layout:
  Rail 26: MP_3Pos carrier
    Position 1: Eppendorf plate (source, water in column 1)
    Position 2: Eppendorf plate (destination, empty)
    Position 3: DiTi_1000ul_SBS_LiHa tip rack

Usage:
  python keyser-testing/test_v1b1_pipette_1000ul_200vol.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from labware_library import DiTi_1000ul_SBS_LiHa_Air, Eppendorf_96_wellplate_250ul_Vb_skirted, MP_3Pos_Corrected
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.tecan.evo import TecanEVO

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

WELLS = ["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1"]


async def main():
  print("=" * 60)
  print("  1000uL Tips — 200uL Volume Test")
  print("=" * 60)

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
  deck.assign_child_resource(carrier, rails=26)

  source = Eppendorf_96_wellplate_250ul_Vb_skirted("source")
  dest = Eppendorf_96_wellplate_250ul_Vb_skirted("dest")
  tip_rack = DiTi_1000ul_SBS_LiHa_Air("tips")
  carrier[0] = source
  carrier[1] = dest
  carrier[2] = tip_rack

  print(f"\n  Rail 26: {tip_rack.model}")
  print(f"    z_start={tip_rack.z_start}  z_max={tip_rack.z_max}")

  print("\nInitializing...")
  await evo.setup()
  print(f"  Channels: {evo.pip.num_channels}")
  print("Ready!")

  try:
    print("\n  Pick up 1000uL tips from col 1...")
    await evo.pip.pick_up_tips(tip_rack.get_items(WELLS))
    print("  Tips picked up!")

    print("\n  Aspirate 200uL from source col 1...")
    await evo.pip.aspirate(source.get_items(WELLS), vols=[200] * 8)
    print("  Aspirated!")

    print("\n  Dispense 200uL into dest col 1 (with 15uL blow-out)...")
    await evo.pip.dispense(dest.get_items(WELLS), vols=[200] * 8, blow_out_air_volume=[15] * 8)
    print("  Dispensed!")

    print("\n  Drop tips into col 1...")
    await evo.pip.drop_tips(tip_rack.get_items(WELLS))
    print("  Tips dropped!")

    print("\n*** 1000uL / 200uL TEST PASSED ***")

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
