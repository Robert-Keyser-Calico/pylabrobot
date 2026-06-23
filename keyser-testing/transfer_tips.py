"""Transfer tips from one column of the rack to another.

Picks up 8 tips from the source column, then drops them into
the destination column of the same tip rack.

Deck layout:
  Rail 16: MP_3Pos carrier, Position 3: tip rack

Usage:
  python keyser-testing/transfer_tips.py [tip_type] <src_col> <dst_col>

  tip_type: 50, 200, or 1000 (default: 50)
  src_col:  1-12 (column to pick up from)
  dst_col:  1-12 (column to drop into)

Examples:
  python keyser-testing/transfer_tips.py 1 2        # 50uL tips, col 1 -> col 2
  python keyser-testing/transfer_tips.py 200 3 6    # 200uL tips, col 3 -> col 6
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from labware_library import (
  DiTi_50ul_SBS_LiHa_Air,
  DiTi_200ul_SBS_LiHa_Air,
  DiTi_1000ul_SBS_LiHa_Air,
  MP_3Pos_Corrected,
)
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.tecan.evo import TecanEVO

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"]

TIP_RACKS = {
  "50": ("DiTi 50uL", DiTi_50ul_SBS_LiHa_Air),
  "200": ("DiTi 200uL", DiTi_200ul_SBS_LiHa_Air),
  "1000": ("DiTi 1000uL", DiTi_1000ul_SBS_LiHa_Air),
}


async def main():
  args = sys.argv[1:]
  tip_type = "50"

  if not args or len(args) < 2:
    print("Usage: transfer_tips.py [tip_type] <src_col> <dst_col>")
    print("  tip_type: 50, 200, or 1000 (default: 50)")
    return

  if args[0] in TIP_RACKS:
    tip_type = args[0]
    args = args[1:]

  if len(args) < 2:
    print("Error: need both source and destination columns.")
    print("Usage: transfer_tips.py [tip_type] <src_col> <dst_col>")
    return

  src_col = int(args[0])
  dst_col = int(args[1])

  if tip_type not in TIP_RACKS:
    print(f"Unknown tip type: {tip_type}. Choose from: {', '.join(TIP_RACKS.keys())}")
    return

  if not 1 <= src_col <= 12:
    print(f"Invalid source column: {src_col}. Must be 1-12.")
    return

  if not 1 <= dst_col <= 12:
    print(f"Invalid destination column: {dst_col}. Must be 1-12.")
    return

  if src_col == dst_col:
    print(f"Source and destination columns are the same ({src_col}). Nothing to do.")
    return

  label, rack_fn = TIP_RACKS[tip_type]
  src_wells = [f"{row}{src_col}" for row in ROWS]
  dst_wells = [f"{row}{dst_col}" for row in ROWS]

  print("=" * 60)
  print(f"  Transfer {label} tips: column {src_col} -> column {dst_col}")
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
  deck.assign_child_resource(carrier, rails=16)

  tip_rack = rack_fn("tips")
  carrier[2] = tip_rack

  print("\nInitializing...")
  await evo.setup()
  print(f"Ready! ({evo.pip.num_channels} channels)")

  try:
    input(f"\nPress Enter to pick up {label} tips from column {src_col}...")
    await evo.pip.pick_up_tips(tip_rack.get_items(src_wells))

    resp = await evo._driver.send_command("C5", command="RTS")
    tip_status = resp["data"][0] if resp and resp.get("data") else 0
    print(f"Tip status after pickup: {tip_status} (255=all mounted)")

    input(f"\nPress Enter to drop tips into column {dst_col}...")
    await evo.pip.drop_tips(tip_rack.get_items(dst_wells))

    resp = await evo._driver.send_command("C5", command="RTS")
    tip_status = resp["data"][0] if resp and resp.get("data") else 0
    print(f"Tip status after drop: {tip_status} (0=no tips)")

    # Raise channels to Z max
    pip_be = evo.pip.backend
    z_range = pip_be._z_range
    num_ch = pip_be.num_channels
    z_params = ",".join([str(z_range)] * num_ch)
    await evo._driver.send_command("C5", command=f"PAZ{z_params}")
    print("Channels raised to Z max.")

    print(f"\nTransfer complete: column {src_col} -> column {dst_col}")

  except Exception as e:
    print(f"\nFailed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

  finally:
    await evo.stop()
    print("Done.")


if __name__ == "__main__":
  asyncio.run(main())
