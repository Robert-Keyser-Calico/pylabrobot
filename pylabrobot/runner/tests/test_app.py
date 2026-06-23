"""Tests for the PyLabRobot Runner API endpoints and WebSocket."""

import asyncio
import json
import warnings

import pytest
from fastapi.testclient import TestClient

from pylabrobot.runner.app import create_app

warnings.filterwarnings("ignore", message=".*total_tip_length.*")


@pytest.fixture
def client():
  app = create_app()
  with TestClient(app) as c:
    yield c


# ============== UI ==============


class TestUI:
  def test_index_returns_html(self, client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "PyLabRobot Runner" in resp.text

  def test_static_files(self, client):
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    assert "connectWebSocket" in resp.text


# ============== Deck ==============


class TestDeck:
  def test_get_deck(self, client):
    resp = client.get("/api/deck")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "children" in data

  def test_get_deck_state(self, client):
    resp = client.get("/api/deck/state")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


# ============== Protocols ==============


class TestProtocols:
  def test_list_protocols(self, client):
    resp = client.get("/api/protocols")
    assert resp.status_code == 200
    assert "protocols" in resp.json()
    assert isinstance(resp.json()["protocols"], list)

  def test_get_starter(self, client):
    resp = client.get("/api/protocols/_starter")
    assert resp.status_code == 200
    data = resp.json()
    assert "code" in data
    assert "async def run" in data["code"]
    assert "deck" in data["code"]

  def test_save_load_delete(self, client):
    code = 'async def run(device):\n  print("test")\n'

    # Save
    resp = client.post(
      "/api/protocols/test_proto",
      json={"code": code},
    )
    assert resp.status_code == 200
    assert resp.json()["saved"] is True

    # Load
    resp = client.get("/api/protocols/test_proto")
    assert resp.status_code == 200
    assert resp.json()["code"] == code
    assert resp.json()["name"] == "test_proto"

    # List includes it
    resp = client.get("/api/protocols")
    assert "test_proto" in resp.json()["protocols"]

    # Delete
    resp = client.delete("/api/protocols/test_proto")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Gone
    resp = client.get("/api/protocols/test_proto")
    assert resp.status_code == 404

  def test_get_nonexistent(self, client):
    resp = client.get("/api/protocols/does_not_exist_xyz")
    assert resp.status_code == 404

  def test_delete_nonexistent(self, client):
    resp = client.delete("/api/protocols/does_not_exist_xyz")
    assert resp.status_code == 404


# ============== Execution ==============


SIMPLE_PROTOCOL = """\
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
deck = EVO150Deck()

async def run(device):
  print("hello from protocol")
"""

BAD_PROTOCOL_NO_DECK = """\
async def run(device):
  pass
"""

BAD_PROTOCOL_NO_RUN = """\
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
deck = EVO150Deck()
"""

SYNTAX_ERROR_PROTOCOL = """\
def this is broken
"""


class TestExecution:
  def test_run_simple_protocol(self, client):
    resp = client.post("/api/run", json={"code": SIMPLE_PROTOCOL})
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"

    # Poll until done
    for _ in range(50):
      status = client.get("/api/run/status").json()
      if status["state"] != "running":
        break
      import time
      time.sleep(0.1)

    assert status["state"] == "completed"
    assert status["error"] is None

  def test_run_no_deck_errors(self, client):
    resp = client.post("/api/run", json={"code": BAD_PROTOCOL_NO_DECK})
    assert resp.status_code == 200

    for _ in range(50):
      status = client.get("/api/run/status").json()
      if status["state"] != "running":
        break
      import time
      time.sleep(0.1)

    assert status["state"] == "error"
    assert "Deck" in status["error"]

  def test_run_no_run_function_errors(self, client):
    resp = client.post("/api/run", json={"code": BAD_PROTOCOL_NO_RUN})
    assert resp.status_code == 200

    for _ in range(50):
      status = client.get("/api/run/status").json()
      if status["state"] != "running":
        break
      import time
      time.sleep(0.1)

    assert status["state"] == "error"
    assert "run" in status["error"]

  def test_run_syntax_error(self, client):
    resp = client.post("/api/run", json={"code": SYNTAX_ERROR_PROTOCOL})
    assert resp.status_code == 200

    for _ in range(50):
      status = client.get("/api/run/status").json()
      if status["state"] != "running":
        break
      import time
      time.sleep(0.1)

    assert status["state"] == "error"

  def test_stop_protocol(self, client):
    long_protocol = """\
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
import asyncio
deck = EVO150Deck()

async def run(device):
  await asyncio.sleep(60)
"""
    client.post("/api/run", json={"code": long_protocol})

    import time
    time.sleep(0.5)

    status = client.get("/api/run/status").json()
    assert status["state"] == "running"

    resp = client.post("/api/run/stop")
    assert resp.status_code == 200

    for _ in range(20):
      status = client.get("/api/run/status").json()
      if status["state"] != "running":
        break
      time.sleep(0.1)

    assert status["state"] == "stopped"

  def test_double_run_rejected(self, client):
    long_protocol = """\
from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
import asyncio
deck = EVO150Deck()

async def run(device):
  await asyncio.sleep(60)
"""
    client.post("/api/run", json={"code": long_protocol})
    import time
    time.sleep(0.3)

    resp = client.post("/api/run", json={"code": SIMPLE_PROTOCOL})
    assert resp.status_code == 409

    client.post("/api/run/stop")
    time.sleep(0.5)

  def test_status_idle_initially(self, client):
    resp = client.get("/api/run/status")
    assert resp.status_code == 200
    assert resp.json()["state"] == "idle"


# ============== Device Management ==============


class TestDeviceManagement:
  def test_status_disconnected_initially(self, client):
    resp = client.get("/api/device/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "disconnected"
    assert data["has_device"] is False

  def test_connect_simulation_without_deck_fails(self, client):
    resp = client.post("/api/device/connect", json={"mode": "simulation"})
    assert resp.status_code == 500
    assert "deck" in resp.json()["detail"].lower()

  def test_connect_simulation_after_run(self, client):
    # Run a protocol to set up the deck
    client.post("/api/run", json={"code": SIMPLE_PROTOCOL})
    import time
    for _ in range(50):
      if client.get("/api/run/status").json()["state"] != "running":
        break
      time.sleep(0.1)

    # Now connect
    resp = client.post("/api/device/connect", json={"mode": "simulation"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "simulation"

    # Status shows connected
    status = client.get("/api/device/status").json()
    assert status["state"] == "connected"
    assert status["has_device"] is True

    # Disconnect
    resp = client.post("/api/device/disconnect")
    assert resp.status_code == 200

    status = client.get("/api/device/status").json()
    assert status["state"] == "disconnected"

  def test_double_connect_rejected(self, client):
    client.post("/api/run", json={"code": SIMPLE_PROTOCOL})
    import time
    for _ in range(50):
      if client.get("/api/run/status").json()["state"] != "running":
        break
      time.sleep(0.1)

    client.post("/api/device/connect", json={"mode": "simulation"})

    resp = client.post("/api/device/connect", json={"mode": "simulation"})
    assert resp.status_code == 500
    assert "Already connected" in resp.json()["detail"]

    client.post("/api/device/disconnect")

  def test_get_config(self, client):
    resp = client.get("/api/device/config")
    assert resp.status_code == 200
    config = resp.json()["config"]
    assert "device_type" in config
    assert config["device_type"] == "TecanEVO"

  def test_update_config(self, client):
    resp = client.put("/api/device/config", json={"diti_count": 4})
    assert resp.status_code == 200
    assert resp.json()["config"]["diti_count"] == 4

    # Reset
    client.put("/api/device/config", json={"diti_count": 8})

  def test_update_config_while_connected_rejected(self, client):
    client.post("/api/run", json={"code": SIMPLE_PROTOCOL})
    import time
    for _ in range(50):
      if client.get("/api/run/status").json()["state"] != "running":
        break
      time.sleep(0.1)

    client.post("/api/device/connect", json={"mode": "simulation"})

    resp = client.put("/api/device/config", json={"diti_count": 4})
    assert resp.status_code == 409

    client.post("/api/device/disconnect")


# ============== System State ==============


class TestSystemState:
  def test_channels_empty_initially(self, client):
    resp = client.get("/api/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert data["num_channels"] == 0
    assert data["channels"] == []

  def test_channels_after_run(self, client):
    client.post("/api/run", json={"code": SIMPLE_PROTOCOL})
    import time
    for _ in range(50):
      if client.get("/api/run/status").json()["state"] != "running":
        break
      time.sleep(0.1)

    resp = client.get("/api/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert data["num_channels"] == 8
    assert len(data["channels"]) == 8
    for ch in data["channels"]:
      assert "index" in ch
      assert "has_tip" in ch
      assert "volume" in ch

  def test_arms_empty_initially(self, client):
    resp = client.get("/api/arms")
    assert resp.status_code == 200
    data = resp.json()
    assert data["arms"] == []

  def test_arms_after_run(self, client):
    client.post("/api/run", json={"code": SIMPLE_PROTOCOL})
    import time
    for _ in range(50):
      if client.get("/api/run/status").json()["state"] != "running":
        break
      time.sleep(0.1)

    resp = client.get("/api/arms")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["arms"]) == 1
    arm = data["arms"][0]
    assert "position" in arm
    assert "x" in arm["position"]
    assert "holding" in arm


# ============== WebSocket ==============


class TestWebSocket:
  def test_ws_connect_and_receive_root(self, client):
    with client.websocket_connect("/ws") as ws:
      ws.send_json({"event": "ready"})
      data = ws.receive_json()
      assert data["event"] == "set_root_resource"
      assert "resource" in data["data"]

  def test_ws_receives_state(self, client):
    with client.websocket_connect("/ws") as ws:
      ws.send_json({"event": "ready"})

      # First message: set_root_resource
      data = ws.receive_json()
      assert data["event"] == "set_root_resource"

      # Second message: set_state
      data = ws.receive_json()
      assert data["event"] == "set_state"


# ============== AI Assistant ==============


class TestAssistant:
  def test_clear_history(self, client):
    resp = client.post("/api/assistant/clear")
    assert resp.status_code == 200
    assert resp.json()["cleared"] is True

  def test_chat_without_api_key_fails(self, client):
    resp = client.post(
      "/api/assistant/chat",
      json={"message": "hello"},
    )
    # Without API key configured, should get 500
    assert resp.status_code == 500
