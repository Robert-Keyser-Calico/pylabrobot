"""Hardware test: move the TecanEVO LiHa and confirm it physically moves.

Safe by construction: Z stays fully retracted (travel height) the entire time,
so XY motion is the standard collision-free travel posture. We read the encoder
position before/after each move to prove the arm actually moved.

Usage:
  PYTHONIOENCODING=utf-8 python calico-testing/test_v1b1_move_liha.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
from pylabrobot.tecan.evo import TecanEVO

logging.basicConfig(level=logging.WARNING)

HOME_X = 45      # 1/10 mm
HOME_Y = 1031    # 1/10 mm
YS = 90          # 1/10 mm y-spacing


async def get_xyz(driver):
  """Read current X, Y, Z encoder positions (1/10 mm)."""
  rx = await driver.send_command("C5", command="RPX0")
  ry = await driver.send_command("C5", command="RPY0")
  rz = await driver.send_command("C5", command="RPZ0")
  x = rx["data"][0] if rx and rx.get("data") else None
  y = ry["data"][0] if ry and ry.get("data") else None
  z = rz["data"][0] if rz and rz.get("data") else None
  return x, y, z


async def main():
  print("=" * 60)
  print("  TecanEVO LiHa Move Test")
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

  print("\nInitializing...")
  await evo.setup()
  pip = evo.pip.backend
  liha = pip.liha
  driver = evo.driver
  n = evo.pip.num_channels
  z_range = pip._z_range
  x_range = await liha.report_x_param(5)
  y_range = (await liha.report_y_param(5))[0]
  print(f"Ready. channels={n}  x_range={x_range}  y_range={y_range}  z_range={z_range}")

  z_up = [z_range] * n

  async def move(label, x, y):
    print(f"\n--- {label}: -> X={x} Y={y} (Z up) ---")
    await liha.set_z_travel_height(z_up)
    await liha.position_absolute_all_axis(x, y, YS, z_up)
    ax, ay, az = await get_xyz(driver)
    print(f"  now X={ax} ({ax / 10:.1f}mm)  Y={ay} ({ay / 10:.1f}mm)  Z={az}")
    return ax, ay

  try:
    bx, by, bz = await get_xyz(driver)
    print(f"\nStart position: X={bx} Y={by} Z={bz}")

    # 1) go to home
    hx, hy = await move("Home", HOME_X, HOME_Y)

    # 2) jog X out by 200 mm (stay well within range), Y unchanged
    target_x = min(HOME_X + 2000, x_range - 100)
    jx, jy = await move("Jog X out", target_x, HOME_Y)
    moved_x = abs(jx - hx)
    print(f"  -> X moved {moved_x / 10:.1f}mm")

    # 3) jog Y out (stay within range)
    target_y = min(HOME_Y + 3000, y_range - 100)
    kx, ky = await move("Jog Y out", target_x, target_y)
    moved_y = abs(ky - jy)
    print(f"  -> Y moved {moved_y / 10:.1f}mm")

    # 4) return home
    await move("Return home", HOME_X, HOME_Y)

    if moved_x > 1000 and moved_y > 1000:
      print("\n*** LIHA MOVE TEST PASSED ***")
    else:
      print("\n*** LIHA MOVE TEST FAILED (insufficient motion) ***")

  finally:
    print("\nStopping...")
    await evo.stop()
    print("Done.")


if __name__ == "__main__":
  asyncio.run(main())
