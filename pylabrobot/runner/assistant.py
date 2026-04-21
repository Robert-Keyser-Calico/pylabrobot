"""LLM-powered code assistant using Vertex AI.

Generates pylabrobot protocol code from natural language descriptions.
Uses the current deck layout and available API methods as context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pylabrobot.resources import Resource

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a lab automation assistant that generates Python code for PyLabRobot protocols.

## Protocol Structure
Protocols define an `async def run(device):` function. The device has:
- `device.pip` — PIP capability for independent-channel liquid handling
- `device.arm` — GripperArm capability for plate handling (optional)
- `device.children[0]` — the Deck resource

## Available PIP Methods
```python
# Pick up tips from tip spots
await device.pip.pick_up_tips(tip_spots)  # tip_spots = tip_rack.get_items(["A1", "B1", ...])

# Aspirate from wells
await device.pip.aspirate(wells, vols=[volume] * n)  # wells = plate.get_items(["A1", ...])

# Dispense to wells
await device.pip.dispense(wells, vols=[volume] * n)

# Drop tips
await device.pip.drop_tips(tip_spots)
```

## Available Arm Methods (plate handling)
```python
# Move a plate from one carrier site to another
await device.arm.move_resource(plate, destination_carrier[site_index])
```

## Accessing Resources
```python
deck = device.children[0]
plate = deck.get_resource("resource_name")
tips = deck.get_resource("tip_rack_name")

# Get specific wells/tips
wells = plate.get_items(["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1"])  # column 1
wells = plate.get_items(["A1", "A2", "A3", "A4"])  # row A, first 4

# Carrier site access
carrier = deck.get_resource("carrier_name")
carrier[0]  # first site
carrier[1]  # second site
```

## Rules
1. Always use `async def run(device):` as the entry point
2. Use `print()` for status messages — they appear in the console
3. Pick up tips before aspirating/dispensing
4. Drop tips when done
5. Volumes are in microliters (uL)
6. The device has {num_channels} channels
7. Generate complete, runnable code — not fragments

## Current Deck Layout
{deck_layout}

Generate only the Python code. No markdown fences. No explanations outside of code comments.
"""


def _describe_deck(root: Resource) -> str:
  """Generate a text description of the current deck layout."""
  lines = []
  for child in root.children:
    loc = child.location
    loc_str = f"x={loc.x:.0f}, y={loc.y:.0f}" if loc else "?"
    lines.append(f'- Carrier "{child.name}" ({type(child).__name__}) at {loc_str}')

    if hasattr(child, "sites"):
      for idx in sorted(child.sites.keys()):
        site = child.sites[idx]
        if site.resource is not None:
          res = site.resource
          lines.append(f'    [{idx}] "{res.name}" ({type(res).__name__})')
        else:
          lines.append(f"    [{idx}] (empty)")

  return "\n".join(lines) if lines else "(empty deck)"


@dataclass
class ChatMessage:
  role: str  # "user" or "assistant"
  content: str


class Assistant:
  """LLM code assistant backed by Vertex AI."""

  def __init__(
    self,
    root_resource: Resource,
    num_channels: int = 8,
    project: Optional[str] = None,
    location: str = "us-central1",
    model: str = "gemini-2.0-flash",
  ):
    self._root = root_resource
    self._num_channels = num_channels
    self._project = project
    self._location = location
    self._model_name = model
    self._history: List[ChatMessage] = []
    self._model = None

  def _get_model(self):
    if self._model is None:
      import vertexai
      from vertexai.generative_models import GenerativeModel

      vertexai.init(project=self._project, location=self._location)
      self._model = GenerativeModel(self._model_name)
    return self._model

  def _build_system_prompt(self) -> str:
    deck_layout = _describe_deck(self._root)
    return SYSTEM_PROMPT.format(
      num_channels=self._num_channels,
      deck_layout=deck_layout,
    )

  async def chat(self, user_message: str) -> str:
    """Send a message and get a code response."""
    import asyncio

    self._history.append(ChatMessage(role="user", content=user_message))

    model = self._get_model()
    system_prompt = self._build_system_prompt()

    contents = [system_prompt]
    for msg in self._history:
      contents.append(f"{msg.role}: {msg.content}")

    response = await asyncio.to_thread(
      model.generate_content, contents
    )

    reply = response.text.strip()

    # Strip markdown code fences if present
    if reply.startswith("```python"):
      reply = reply[len("```python"):].strip()
    if reply.startswith("```"):
      reply = reply[3:].strip()
    if reply.endswith("```"):
      reply = reply[:-3].strip()

    self._history.append(ChatMessage(role="assistant", content=reply))
    return reply

  def clear_history(self) -> None:
    self._history.clear()
