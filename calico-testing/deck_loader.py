"""Load a deck layout from a JSON config file.

Usage:
  from deck_loader import load_deck
  deck, tip_racks = load_deck("deck_layout.json")
"""

import json
import os

from labware_library import (
  DeepWell_96_Round_Corrected,
  DiTi_50ul_SBS_LiHa_Air,
  DiTi_200ul_SBS_LiHa_Air,
  DiTi_1000ul_SBS_LiHa_Air,
  Eppendorf_96_wellplate_250ul_Vb_skirted,
  MP_3Pos_Corrected,
)
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck

LABWARE_REGISTRY = {
  "MP_3Pos_Corrected": MP_3Pos_Corrected,
  "Eppendorf_96_wellplate_250ul_Vb_skirted": Eppendorf_96_wellplate_250ul_Vb_skirted,
  "DeepWell_96_Round_Corrected": DeepWell_96_Round_Corrected,
  "DiTi_50ul_SBS_LiHa_Air": DiTi_50ul_SBS_LiHa_Air,
  "DiTi_200ul_SBS_LiHa_Air": DiTi_200ul_SBS_LiHa_Air,
  "DiTi_1000ul_SBS_LiHa_Air": DiTi_1000ul_SBS_LiHa_Air,
}

DECK_REGISTRY = {
  "EVO150Deck": EVO150Deck,
}

TIP_PREFIXES = ("DiTi_",)


def load_deck(config_path=None):
  """Load deck layout from JSON config.

  Args:
    config_path: Path to JSON config file. Defaults to deck_layout.json
                 in the same directory as this module.

  Returns:
    (deck, tip_racks) where deck is an EVO150Deck and tip_racks is a dict
    mapping tip size labels (e.g. "50", "200", "1000") to tip rack resources.
  """
  if config_path is None:
    config_path = os.path.join(os.path.dirname(__file__), "deck_layout.json")

  with open(config_path) as f:
    config = json.load(f)

  deck_cls = DECK_REGISTRY[config["deck_type"]]
  deck = deck_cls()

  tip_racks = {}

  for carrier_cfg in config["carriers"]:
    carrier_cls = LABWARE_REGISTRY[carrier_cfg["type"]]
    carrier = carrier_cls(carrier_cfg["name"])
    deck.assign_child_resource(carrier, rails=carrier_cfg["rails"])

    for lw in carrier_cfg.get("labware", []):
      lw_cls = LABWARE_REGISTRY[lw["type"]]
      resource = lw_cls(lw["name"])
      carrier[lw["pos"]] = resource

      if lw["type"].startswith(TIP_PREFIXES):
        size = lw["type"].split("_")[1].replace("ul", "")
        tip_racks[size] = resource

  return deck, tip_racks
