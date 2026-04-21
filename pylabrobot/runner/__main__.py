"""CLI entry point for the PyLabRobot Protocol Runner.

Usage:
  python -m pylabrobot.runner                # default EVO150 demo deck
  python -m pylabrobot.runner --port 8080    # custom port
"""

import argparse
import logging
import webbrowser

import uvicorn


def build_demo_deck():
  """Build a demo EVO150 deck with carriers and labware."""
  from pylabrobot.resources import Coordinate
  from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
  from pylabrobot.resources.tecan.plate_carriers import MP_3Pos
  from pylabrobot.resources.tecan.tip_carriers import DiTi_3Pos
  from pylabrobot.resources.tecan.tip_racks import DiTi_50ul_SBS_LiHa
  from pylabrobot.resources.agilent.plates import agilent_96_wellplate_150uL_Vb

  deck = EVO150Deck()

  carrier1 = MP_3Pos("plate_carrier")
  deck.assign_child_resource(carrier1, rails=16)
  carrier1[0] = agilent_96_wellplate_150uL_Vb("source_plate")
  carrier1[1] = agilent_96_wellplate_150uL_Vb("dest_plate")

  tip_carrier = DiTi_3Pos("tip_carrier")
  deck.assign_child_resource(tip_carrier, rails=10)
  tip_carrier[0] = DiTi_50ul_SBS_LiHa("tips_1")
  tip_carrier[1] = DiTi_50ul_SBS_LiHa("tips_2")

  return deck


def main():
  logging.basicConfig(
    filename="runner.log",
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    force=True,
  )

  parser = argparse.ArgumentParser(description="PyLabRobot Protocol Runner")
  parser.add_argument("--port", type=int, default=5051, help="Server port (default: 5051)")
  parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host")
  parser.add_argument("--no-browser", action="store_true", help="Don't open browser on start")
  parser.add_argument("--vertex-project", type=str, default=None, help="GCP project for Vertex AI")
  parser.add_argument("--vertex-location", type=str, default="us-central1", help="Vertex AI region")
  parser.add_argument("--vertex-model", type=str, default="gemini-2.0-flash", help="Vertex AI model")
  args = parser.parse_args()

  deck = build_demo_deck()

  from pylabrobot.runner.app import create_app
  from pylabrobot.runner.simulation import create_simulated_device

  import asyncio

  device = create_simulated_device(deck, num_channels=8, has_arm=True)
  asyncio.run(device.setup())
  print("  Simulated device ready (8 channels, gripper arm)")

  app = create_app(
    deck,
    device=device,
    vertex_project=args.vertex_project,
    vertex_location=args.vertex_location,
    vertex_model=args.vertex_model,
  )

  if not args.no_browser:
    import threading

    threading.Timer(1.5, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()

  print(f"\n  PyLabRobot Runner: http://{args.host}:{args.port}\n")
  uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
  main()
