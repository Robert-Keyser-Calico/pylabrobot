"""Hardware test: TecanEVO v1b1 RoMa plate handling.

Tests RoMa pick/place via the high-level move_resource API.

Route: carrier_r4[0] -> carrier_r16[0] -> carrier_r26[0] -> carrier_r4[0]

Deck layout (matches jog_ui.py):
  Rail  4: MP_3Pos carrier ("carrier_r4")  — plate in pos 0, pos 1-2 empty
  Rail 16: MP_3Pos carrier ("carrier_r16") — all empty
  Rail 26: MP_3Pos carrier ("carrier_r26") — all empty

Usage:
  python calico-testing/test_v1b1_roma.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from labware_library import Eppendorf_96_wellplate_250ul_Vb_skirted, MP_3Pos_Corrected
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.tecan.evo import TecanEVO
from pylabrobot.tecan.evo.params import TecanRoMaParams

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

# Slow speeds for testing — defaults are x=10000, y=5000, z=1300, r=5000
SLOW_PARAMS = TecanRoMaParams(
  speed_x=3000,
  speed_y=2000,
  speed_z=800,
  speed_r=2000,
  accel_y=800,
  accel_r=800,
)


async def main():
  print("=" * 60)
  print("  TecanEVO v1b1 RoMa Multi-Position Test")
  print("  Using high-level move_resource API")
  print("  Deck layout matches jog_ui.py")
  print("=" * 60)

  # --- Deck setup (matching jog_ui.py) ---
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

  carrier_r4 = MP_3Pos_Corrected("carrier_r4")
  carrier_r16 = MP_3Pos_Corrected("carrier_r16")
  carrier_r26 = MP_3Pos_Corrected("carrier_r26")
  deck.assign_child_resource(carrier_r4, rails=4)
  deck.assign_child_resource(carrier_r16, rails=16)
  deck.assign_child_resource(carrier_r26, rails=26)

  plate = Eppendorf_96_wellplate_250ul_Vb_skirted("plate")
  carrier_r4[0] = plate

  print("\nDeck layout:")
  print(f"  Rail  4: {carrier_r4.name}   [plate in pos 0]")
  print(f"  Rail 16: {carrier_r16.name}  [empty]")
  print(f"  Rail 26: {carrier_r26.name}  [empty]")
  print("\nRoute: r4[0] -> r16[0] -> r26[0] -> r4[0]")

  print("\nInitializing...")
  try:
    await evo.setup()
    print(f"  Channels: {evo.pip.num_channels}")
    print(f"  RoMa: {'available' if evo.arm else 'not available'}")
    print("Ready!")
  except Exception as e:
    print(f"Init FAILED: {e}")
    import traceback
    traceback.print_exc()
    return

  assert evo.arm is not None, "RoMa arm not initialized"

  try:
    moves = [
      (carrier_r16[0], "carrier_r4[0] -> carrier_r16[0]"),
      (carrier_r26[0], "carrier_r16[0] -> carrier_r26[0]"),
      (carrier_r4[0], "carrier_r26[0] -> carrier_r4[0] (return)"),
    ]

    for i, (destination, label) in enumerate(moves, 1):
      print(f"\n--- Step {i}: {label} ---")
      print(f"  Plate at: {plate.parent.parent.name}[{plate.parent.name}]")
      await asyncio.sleep(2)

      await evo.arm.move_resource(
        plate, destination,
        backend_params=SLOW_PARAMS,
      )
      print(f"  Plate now at: {plate.parent.parent.name}[{plate.parent.name}]")

    # Park
    await evo.arm.backend.park()
    print("\nRoMa parked!")

    print("\n*** ROMA MULTI-POSITION TEST PASSED ***")

  except Exception as e:
    print(f"\nTest FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

  finally:
    print("\nStopping...")
    await evo.stop()
    print("Done.")


if __name__ == "__main__":
  asyncio.run(main())
