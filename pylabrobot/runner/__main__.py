"""CLI entry point for the PyLabRobot Protocol Runner.

Usage:
  python -m pylabrobot.runner
  python -m pylabrobot.runner --port 8080
  python -m pylabrobot.runner --vertex-project my-gcp-project
"""

import argparse
import logging
import webbrowser

import uvicorn


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
  parser.add_argument("--lib", type=str, action="append", default=[], help="Add directory to Python path (for local labware imports)")
  parser.add_argument("--vertex-project", type=str, default=None, help="GCP project for Vertex AI")
  parser.add_argument("--vertex-location", type=str, default="us-central1", help="Vertex AI region")
  parser.add_argument("--vertex-model", type=str, default="gemini-2.0-flash", help="Vertex AI model")
  args = parser.parse_args()

  import sys

  for lib_path in args.lib:
    sys.path.insert(0, lib_path)

  from pylabrobot.runner.app import create_app

  app = create_app(
    vertex_project=args.vertex_project,
    vertex_location=args.vertex_location,
    vertex_model=args.vertex_model,
  )

  if not args.no_browser:
    import threading

    threading.Timer(1.5, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()

  print(f"\n  PyLabRobot Runner: http://{args.host}:{args.port}")
  print("  Write a protocol with deck setup + run(), then click Run.\n")
  uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
  main()
