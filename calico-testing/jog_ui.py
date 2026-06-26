"""Web-based jog UI for Tecan EVO.

Flask server with real-time position display and keyboard-driven jogging
for both LiHa and RoMa arms.

Numpad controls:
  LiHa:
    4/6  X left/right
    8/2  Y back/forward (8=away from operator, 2=toward operator)
    +/-  Z down/up (+=toward deck, -=away from deck)
    7/9  Step size down/up

  RoMa:
    Arrow keys: X left/right, Y forward/back
    PageUp/PageDown: Z up/down
    Home/End: R rotate

Usage:
  python keyser-testing/jog_ui.py
  Then open http://localhost:5050
"""

import asyncio
import json
import logging
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, render_template_string, request

logging.basicConfig(level=logging.WARNING)

# Globals for the EVO connection
evo = None
driver = None
loop = None
tip_racks = {}  # populated by build_deck()

STEP_SIZES = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]
current_step_idx = 4  # start at 5mm
current_arm = "liha"

POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "taught_positions.json")
LABWARE_FILE = os.path.join(os.path.dirname(__file__), "labware_edits.json")


def run_async(coro):
  """Run an async coroutine from sync Flask context."""
  future = asyncio.run_coroutine_threadsafe(coro, loop)
  return future.result(timeout=30)


app = Flask(__name__)
app.json.sort_keys = False

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Tecan EVO Jog</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #0f172a; color: #e2e8f0;
         display: flex; flex-direction: column; height: 100vh; }
  .header { background: #1e293b; padding: 12px 20px; display: flex; justify-content: space-between;
            align-items: center; border-bottom: 2px solid #334155; }
  .header h1 { font-size: 18px; color: #60a5fa; }
  .status { font-size: 12px; color: #64748b; }
  .main { display: flex; flex: 1; overflow: hidden; }

  .panel { padding: 16px; overflow-y: auto; }
  .log-col { width: 20%; border-right: 1px solid #334155; display: flex; flex-direction: column; }
  .left { width: 45%; border-right: 1px solid #334155; }
  .right { width: 35%; }

  .position-box { background: #1e293b; border-radius: 8px; padding: 16px; margin-bottom: 12px;
                  border: 1px solid #334155; }
  .position-box h2 { font-size: 14px; color: #60a5fa; margin-bottom: 10px; text-transform: uppercase;
                     letter-spacing: 1px; }
  .position-box.active { border-color: #60a5fa; box-shadow: 0 0 10px rgba(38,139,210,0.3); }

  .pos-grid { display: grid; grid-template-columns: 60px 1fr 80px; gap: 4px; align-items: center; }
  .pos-label { font-weight: bold; color: #cbd5e1; font-size: 13px; }
  .pos-bar { background: #0f172a; border-radius: 4px; height: 24px; position: relative; overflow: hidden; }
  .pos-fill { height: 100%; background: linear-gradient(90deg, #1e3a5f, #3b6ea5); border-radius: 4px;
              transition: width 0.3s; }
  .pos-value { font-family: 'Courier New', monospace; font-size: 14px; text-align: right; }

  .controls { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
  .btn { padding: 6px 14px; border: 1px solid #334155; background: #1e293b; color: #e2e8f0;
         border-radius: 4px; cursor: pointer; font-size: 12px; }
  .btn:hover { background: #334155; }
  .btn.active { background: #60a5fa; border-color: #60a5fa; color: #ffffff; }
  .btn.small { padding: 4px 8px; font-size: 11px; }

  .step-display { background: #0f172a; padding: 8px 16px; border-radius: 4px;
                  font-family: monospace; font-size: 16px; text-align: center;
                  color: #60a5fa; margin-bottom: 12px; }

  .key-help { font-size: 11px; color: #64748b; line-height: 1.8; }
  .key { display: inline-block; background: #1e293b; padding: 2px 6px; border-radius: 3px;
         font-family: monospace; font-size: 11px; min-width: 20px; text-align: center;
         border: 1px solid #334155; color: #e2e8f0; }

  .teach-section { margin-top: 12px; }
  .teach-row { display: flex; gap: 8px; margin-bottom: 6px; align-items: center; }
  .teach-row input { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 4px 8px;
                     border-radius: 4px; font-size: 12px; width: 120px; }
  .teach-row select { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 4px 8px;
                      border-radius: 4px; font-size: 12px; }

  .log { background: #0f172a; border-radius: 4px; padding: 8px; font-family: monospace;
         font-size: 11px; flex: 1; overflow-y: auto; color: #64748b; }
  .log .entry { margin-bottom: 2px; }
  .log .ok { color: #34d399; }
  .log .err { color: #f87171; }

  .pos-readout { background: #0f172a; padding: 6px 12px; border-radius: 4px;
                 font-family: 'Courier New', monospace; font-size: 12px; color: #5eead4;
                 margin-bottom: 10px; }

  .deck-map { background: #0f172a; border-radius: 8px; padding: 8px; margin-top: 12px;
              border: 1px solid #334155; cursor: crosshair; }
  .deck-map svg { width: 100%; display: block; }
  .deck-map .lw-rect { stroke: #334155; stroke-width: 1; cursor: pointer; opacity: 0.85; }
  .deck-map .lw-rect:hover { opacity: 1; stroke: #60a5fa; stroke-width: 2; }
  .deck-map .lw-label { font-size: 7px; fill: #e2e8f0; pointer-events: none;
                         font-family: 'Segoe UI', sans-serif; }
  .deck-map .arm-marker { pointer-events: none; }

  .confirm-modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                   background: rgba(0,0,0,0.7); z-index: 1000; justify-content: center;
                   align-items: center; }
  .confirm-modal.visible { display: flex; }
  .confirm-box { background: #1e293b; border: 2px solid #60a5fa; border-radius: 8px;
                 padding: 24px; max-width: 400px; text-align: center; }
  .confirm-box h3 { color: #60a5fa; margin-bottom: 12px; }
  .confirm-box .coords { font-family: monospace; font-size: 14px; color: #5eead4; margin: 12px 0; }
  .confirm-box .hint { font-size: 12px; color: #64748b; margin-top: 12px; }

  .saved-positions { margin-top: 12px; }
  .saved-pos { display: flex; justify-content: space-between; align-items: center;
               padding: 4px 8px; background: #1e293b; border-radius: 4px; margin-bottom: 4px;
               font-size: 12px; }
</style>
</head>
<body>
<div class="header">
  <h1>Tecan EVO Jog & Teach</h1>
  <div style="display:flex;align-items:center;gap:12px;">
    <button class="btn" id="btn-connect" onclick="toggleConnect()" style="background:#334155">Connect</button>
    <div class="status" id="status">Disconnected</div>
  </div>
</div>
<div class="main">
  <!-- Log column -->
  <div class="panel log-col">
    <h2 style="font-size:14px;color:#60a5fa;margin-bottom:8px;">LOG</h2>
    <div class="log" id="log"></div>
  </div>

  <div class="panel left">
    <!-- Arm selector -->
    <div class="controls">
      <button class="btn active" id="btn-liha" onclick="setArm('liha')">LiHa (Pipette)</button>
      <button class="btn" id="btn-roma" onclick="setArm('roma')">RoMa (Plate)</button>
    </div>

    <!-- Step size -->
    <div class="step-display">
      Step: <span id="step-size">5.0</span> mm
      <span style="font-size:11px;color:#334155;margin-left:8px">
        (<span class="key">7</span> smaller / <span class="key">9</span> bigger)
      </span>
    </div>

    <!-- LiHa position -->
    <div class="position-box active" id="box-liha">
      <h2>LiHa Position</h2>
      <div class="pos-grid">
        <span class="pos-label">X</span>
        <div class="pos-bar"><div class="pos-fill" id="liha-x-bar" style="width:50%"></div></div>
        <span class="pos-value" id="liha-x">—</span>

        <span class="pos-label">Y</span>
        <div class="pos-bar"><div class="pos-fill" id="liha-y-bar" style="width:50%"></div></div>
        <span class="pos-value" id="liha-y">—</span>

        <span class="pos-label">Z1</span>
        <div class="pos-bar"><div class="pos-fill" id="liha-z-bar" style="width:50%"></div></div>
        <span class="pos-value" id="liha-z">—</span>

        <span class="pos-label" id="liha-ztip-row1" style="display:none;color:#fbbf24;">Z tip</span>
        <div class="pos-bar" id="liha-ztip-row2" style="display:none;"><div class="pos-fill" id="liha-ztip-bar" style="width:50%;background:linear-gradient(90deg,#5c3d1a,#b8942a);"></div></div>
        <span class="pos-value" id="liha-ztip-row3" style="display:none;color:#fbbf24;" ><span id="liha-ztip">—</span></span>
      </div>
      <div id="liha-tip-label" style="margin-top:4px;font-size:10px;color:#fbbf24;text-align:right;display:none;"></div>
    </div>

    <!-- Direct XYZ input -->
    <div style="background:#1e293b;border-radius:8px;padding:10px;margin-bottom:12px;border:1px solid #334155;">
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
        <span style="font-size:12px;color:#60a5fa;font-weight:bold;">MOVE TO:</span>
        <label style="font-size:11px;color:#cbd5e1;">X</label>
        <input type="number" id="input-x" step="0.1" style="width:70px;background:#0f172a;border:1px solid #444;color:#e2e8f0;padding:3px 6px;border-radius:4px;font-size:12px;font-family:monospace;">
        <label style="font-size:11px;color:#cbd5e1;">Y</label>
        <input type="number" id="input-y" step="0.1" style="width:70px;background:#0f172a;border:1px solid #444;color:#e2e8f0;padding:3px 6px;border-radius:4px;font-size:12px;font-family:monospace;">
        <label style="font-size:11px;color:#cbd5e1;" id="input-z-label">Z</label>
        <input type="number" id="input-z" step="0.1" style="width:70px;background:#0f172a;border:1px solid #444;color:#e2e8f0;padding:3px 6px;border-radius:4px;font-size:12px;font-family:monospace;">
        <button class="btn small" onclick="directMove()" style="border-color:#34d399;color:#34d399;">Go</button>
        <span style="font-size:10px;color:#334155;" id="input-coords-hint">mm (Tecan coords)</span>
      </div>
    </div>

    <!-- RoMa position -->
    <div class="position-box" id="box-roma">
      <h2>RoMa Position</h2>
      <div class="pos-grid">
        <span class="pos-label">X</span>
        <div class="pos-bar"><div class="pos-fill" id="roma-x-bar" style="width:50%"></div></div>
        <span class="pos-value" id="roma-x">—</span>

        <span class="pos-label">Y</span>
        <div class="pos-bar"><div class="pos-fill" id="roma-y-bar" style="width:50%"></div></div>
        <span class="pos-value" id="roma-y">—</span>

        <span class="pos-label">Z</span>
        <div class="pos-bar"><div class="pos-fill" id="roma-z-bar" style="width:50%"></div></div>
        <span class="pos-value" id="roma-z">—</span>

        <span class="pos-label">R</span>
        <div class="pos-bar"><div class="pos-fill" id="roma-r-bar" style="width:50%"></div></div>
        <span class="pos-value" id="roma-r">—</span>

        <span class="pos-label">G</span>
        <div class="pos-bar"><div class="pos-fill" id="roma-g-bar" style="width:50%"></div></div>
        <span class="pos-value" id="roma-g">—</span>
      </div>
      <div class="controls" style="margin-top:8px">
        <button class="btn small" onclick="sendJog('roma','g',-1)">G Close ←</button>
        <button class="btn small" onclick="sendJog('roma','g',1)">G Open →</button>
        <button class="btn small" onclick="sendAction('gripper_open')">Full Open</button>
      </div>
    </div>

    <!-- Key help -->
    <div class="key-help">
      <b>LiHa (Numpad):</b>
      <span class="key">4</span>/<span class="key">6</span> X &nbsp;
      <span class="key">8</span>/<span class="key">2</span> Y back/fwd &nbsp;
      <span class="key">+</span>/<span class="key">-</span> Z down/up &nbsp;
      <span class="key">7</span>/<span class="key">9</span> Step
      <br>
      <b>RoMa (Arrows):</b>
      <span class="key">←</span>/<span class="key">→</span> X &nbsp;
      <span class="key">↑</span>/<span class="key">↓</span> Y &nbsp;
      <span class="key">PgUp</span>/<span class="key">PgDn</span> Z &nbsp;
      <span class="key">Home</span>/<span class="key">End</span> R &nbsp;
      <span class="key">[</span>/<span class="key">]</span> G close/open
    </div>

    <!-- Deck map -->
    <div class="deck-map">
      <svg id="deck-svg" viewBox="0 0 960 400" preserveAspectRatio="xMidYMid meet">
        <rect x="0" y="0" width="960" height="400" fill="#0f172a" />
        <text x="480" y="395" text-anchor="middle" fill="#334155" font-size="10"
              font-family="sans-serif">&#9650; OPERATOR (front)</text>
        <g id="deck-labware"></g>
        <g id="deck-arm" class="arm-marker"></g>
      </svg>
    </div>
  </div>

  <div class="panel right">
    <!-- Labware Inspector -->
    <div>
      <h2 style="font-size:14px;color:#60a5fa;margin-bottom:8px;">LABWARE</h2>
      <div class="controls" id="labware-tabs"></div>
      <div id="labware-detail" style="background:#1e293b;border-radius:8px;padding:12px;
           border:1px solid #334155;font-size:12px;margin-bottom:12px;">
        <i style="color:#334155">Select labware above</i>
      </div>
    </div>

    <!-- Live position readout -->
    <div class="pos-readout" id="pos-readout">LiHa: X=—  Y=—  Z=—</div>

    <!-- Teach -->
    <div>
      <h2 style="font-size:14px;color:#60a5fa;margin-bottom:8px;">TEACH FROM CURRENT Z</h2>
      <div class="teach-row">
        <label style="color:#cbd5e1;font-size:12px;width:70px">Mounted:</label>
        <select id="teach-tip-type" style="width:140px" onchange="updateTipInfo()">
          <option value="none">No tip</option>
          <option value="50ul">DiTi 50µL (ext 470)</option>
          <option value="200ul">DiTi 200µL (ext 475)</option>
          <option value="1000ul">DiTi 1000µL (ext 851)</option>
        </select>
        <span id="tip-ext-info" style="font-size:11px;color:#64748b;margin-left:4px"></span>
      </div>
      <div class="teach-row" style="margin-top:4px">
        <select id="teach-field" style="width:110px">
          <option value="z_start">z_start</option>
          <option value="z_dispense">z_dispense</option>
          <option value="z_max">z_max</option>
        </select>
        <select id="teach-labware"></select>
        <button class="btn" onclick="teachLabware()">Set</button>
        <button class="btn" onclick="undoTeach()" style="border-color:#fbbf24;color:#fbbf24">Undo</button>
      </div>
      <div class="teach-row" style="margin-top:6px">
        <input type="text" id="teach-label" placeholder="Label (e.g. tip_top)" style="width:160px">
        <button class="btn" onclick="recordPosition('liha')">Record LiHa</button>
        <button class="btn" onclick="recordPosition('roma')">Record RoMa</button>
      </div>
    </div>

    <!-- Teach checklist -->
    <div style="margin-top:12px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <h2 style="font-size:14px;color:#60a5fa;">TEACH CHECKLIST</h2>
        <div style="display:flex;gap:4px;align-items:center;">
          <span style="font-size:11px;color:#64748b;">Go To:</span>
          <button class="btn small active" id="btn-goto-z" onclick="setGotoMode('z')">Z only</button>
          <button class="btn small" id="btn-goto-xyz" onclick="setGotoMode('xyz')">XYZ</button>
        </div>
      </div>
      <div id="teach-checklist" style="font-size:11px;font-family:monospace;"></div>
    </div>

    <!-- Quick actions -->
    <div style="margin-top:12px;">
      <h2 style="font-size:14px;color:#60a5fa;margin-bottom:8px;">ACTIONS</h2>
      <div class="controls">
        <button class="btn" onclick="sendAction('home')">Home LiHa</button>
        <button class="btn" onclick="sendAction('z_up')">Z Up (Clear)</button>
        <button class="btn" onclick="sendAction('park_roma')">Park RoMa</button>
        <button class="btn" onclick="sendAction('tips_status')">Check Tips</button>
        <button class="btn" onclick="sendAction('eject_tips')" style="border-color:#fbbf24">Eject Tips</button>
        <button class="btn" onclick="sendAction('ree')">Axis Status</button>
      </div>
      <details style="margin-top:4px">
        <summary style="cursor:pointer;font-size:11px;color:#334155">Lamp & Power Controls</summary>
        <div class="controls" style="margin-top:4px">
          <button class="btn small" onclick="sendAction('lamp_green')" style="border-color:#34d399">Lamp Green</button>
          <button class="btn small" onclick="sendAction('lamp_off')">Lamp Off</button>
          <button class="btn small" onclick="sendAction('lamp_test')">Lamp Test</button>
          <button class="btn small" onclick="sendAction('power_on')" style="border-color:#fbbf24">Motor Power</button>
          <button class="btn small" onclick="sendAction('power_off')">Power Off</button>
        </div>
      </details>
    </div>

    <!-- Tip Management -->
    <div style="margin-top:12px;">
      <h2 style="font-size:14px;color:#60a5fa;margin-bottom:8px;">TIP MANAGEMENT</h2>
      <div class="controls" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <select id="tip-type" style="background:#1e293b;color:#e2e8f0;border:1px solid #334155;padding:4px 8px;border-radius:4px;">
          <option value="50">50uL (rail 4)</option>
          <option value="200">200uL (rail 16)</option>
          <option value="1000">1000uL (rail 26)</option>
        </select>
        <label style="font-size:12px;color:#64748b;">Col:</label>
        <input type="number" id="tip-col" value="1" min="1" max="12" style="width:50px;background:#1e293b;color:#e2e8f0;border:1px solid #334155;padding:4px;border-radius:4px;">
        <button class="btn" onclick="pickUpTips()" style="border-color:#34d399">Pick Up</button>
        <button class="btn" onclick="dropTips()" style="border-color:#fbbf24">Drop</button>
      </div>
    </div>

    <!-- Saved positions -->
    <div class="saved-positions" style="margin-top:12px;">
      <h2 style="font-size:14px;color:#60a5fa;margin-bottom:8px;">SAVED POSITIONS</h2>
      <div id="saved-list"></div>
    </div>

  </div>
</div>

<!-- XYZ Confirmation Modal -->
<div class="confirm-modal" id="confirm-modal">
  <div class="confirm-box">
    <h3>Confirm XY Move</h3>
    <div id="confirm-msg">Move LiHa to labware position?</div>
    <div class="coords" id="confirm-coords">X=0.0  Y=0.0  Z=0.0</div>
    <div class="hint">Press <span class="key">Enter</span> to move &nbsp; <span class="key">Esc</span> to cancel</div>
  </div>
</div>

<script>
let arm = 'liha';
let stepIdx = 4;
const STEPS = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0];
const TIP_EXT = {none: 0, '50ul': 470, '200ul': 475, '1000ul': 851};
let gotoMode = 'z';
let pendingGoto = null;

function setGotoMode(mode) {
  gotoMode = mode;
  document.getElementById('btn-goto-z').className = 'btn small' + (mode==='z' ? ' active' : '');
  document.getElementById('btn-goto-xyz').className = 'btn small' + (mode==='xyz' ? ' active' : '');
}

function updateTipInfo() {
  const tip = document.getElementById('teach-tip-type').value;
  const ext = TIP_EXT[tip] || 0;
  const info = document.getElementById('tip-ext-info');
  const zLabel = document.getElementById('input-z-label');
  const hint = document.getElementById('input-coords-hint');
  // Sync tip management dropdown
  const mgmt = TEACH_TO_MGMT[tip];
  if (mgmt) document.getElementById('tip-type').value = mgmt;
  if (ext > 0) {
    info.textContent = 'Z offset: -' + ext + ' (' + (ext/10).toFixed(1) + 'mm)';
    info.style.color = '#fbbf24';
    zLabel.textContent = 'Z tip';
    zLabel.style.color = '#fbbf24';
    hint.textContent = 'mm — Z = tip end position';
  } else {
    info.textContent = '';
    zLabel.textContent = 'Z';
    zLabel.style.color = '#aaa';
    hint.textContent = 'mm (Tecan coords)';
  }
}
let polling = null;

function setArm(a) {
  arm = a;
  document.getElementById('btn-liha').className = 'btn' + (a==='liha' ? ' active' : '');
  document.getElementById('btn-roma').className = 'btn' + (a==='roma' ? ' active' : '');
  document.getElementById('box-liha').className = 'position-box' + (a==='liha' ? ' active' : '');
  document.getElementById('box-roma').className = 'position-box' + (a==='roma' ? ' active' : '');
}

function updateStep() {
  document.getElementById('step-size').textContent = STEPS[stepIdx].toFixed(1);
}

function log(msg, cls) {
  const el = document.getElementById('log');
  const entry = document.createElement('div');
  entry.className = 'entry ' + (cls || '');
  entry.textContent = msg;
  el.appendChild(entry);
  el.scrollTop = el.scrollHeight;
}

const TEACH_TO_MGMT = {'50ul': '50', '200ul': '200', '1000ul': '1000'};
const MGMT_TO_TEACH = {'50': '50ul', '200': '200ul', '1000': '1000ul'};

function syncMountedTip(data) {
  if (data && data.mounted_tip !== undefined) {
    document.getElementById('teach-tip-type').value = data.mounted_tip;
    const mgmt = TEACH_TO_MGMT[data.mounted_tip];
    if (mgmt) document.getElementById('tip-type').value = mgmt;
    updateTipInfo();
    log('  Tips: ' + (data.mounted_tip === 'none' ? 'none mounted' : data.mounted_tip + ' mounted'), 'ok');
  }
}

let busy = false;

async function sendJog(armName, axis, direction) {
  if (!isConnected) { log('Not connected — click Connect first', 'err'); return; }
  if (busy) { log('Busy — wait for move to finish', 'err'); return; }
  busy = true;
  document.getElementById('status').textContent = 'Moving...';
  document.getElementById('status').style.color = '#fbbf24';
  const cmd = armName.toUpperCase() + ' ' + axis + (direction > 0 ? '+' : '-') + ' ' + STEPS[stepIdx] + 'mm';
  log('> ' + cmd, '');
  try {
    const resp = await fetch('/jog', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({arm: armName, axis: axis, direction: direction, step: STEPS[stepIdx]})
    });
    const data = await resp.json();
    if (data.error) { log('  ERR: ' + data.error, 'err'); }
    else {
      updatePositions(data);
      if (data.cmd) { log('  ' + data.cmd, 'ok'); }
    }
  } catch(e) { log('  Failed: ' + e, 'err'); }
  finally {
    busy = false;
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').style.color = '#34d399';
  }
}

async function sendAction(action) {
  if (busy) { log('Busy — wait for current operation', 'err'); return; }
  busy = true;
  document.getElementById('status').textContent = 'Busy...';
  document.getElementById('status').style.color = '#fbbf24';
  log('> ACTION: ' + action, '');
  try {
    const resp = await fetch('/action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: action})
    });
    const data = await resp.json();
    if (data.message) log('  ' + data.message, 'ok');
    if (data.error) log('  ' + data.error, 'err');
    updatePositions(data);
    syncMountedTip(data);
    if (data.saved) loadSaved();
  } catch(e) { log('  Action failed: ' + e, 'err'); }
  finally {
    busy = false;
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').style.color = '#34d399';
  }
}

async function pickUpTips() {
  const tipType = document.getElementById('tip-type').value;
  const col = parseInt(document.getElementById('tip-col').value);
  if (col < 1 || col > 12) { log('Column must be 1-12', 'err'); return; }
  if (busy) { log('Busy — wait for current operation', 'err'); return; }
  busy = true;
  document.getElementById('status').textContent = 'Picking up tips...';
  document.getElementById('status').style.color = '#fbbf24';
  log('> PICK UP: ' + tipType + 'uL tips, col ' + col, '');
  try {
    const resp = await fetch('/action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'pick_up_tips', tip_type: tipType, column: col})
    });
    const data = await resp.json();
    if (data.message) log('  ' + data.message, 'ok');
    if (data.error) log('  ' + data.error, 'err');
    updatePositions(data);
    syncMountedTip(data);
  } catch(e) { log('  Pick up failed: ' + e, 'err'); }
  finally {
    busy = false;
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').style.color = '#34d399';
  }
}

async function dropTips() {
  const tipType = document.getElementById('tip-type').value;
  const col = parseInt(document.getElementById('tip-col').value);
  if (col < 1 || col > 12) { log('Column must be 1-12', 'err'); return; }
  if (busy) { log('Busy — wait for current operation', 'err'); return; }
  busy = true;
  document.getElementById('status').textContent = 'Dropping tips...';
  document.getElementById('status').style.color = '#fbbf24';
  log('> DROP: ' + tipType + 'uL tips, col ' + col, '');
  try {
    const resp = await fetch('/action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'drop_tips', tip_type: tipType, column: col})
    });
    const data = await resp.json();
    if (data.message) log('  ' + data.message, 'ok');
    if (data.error) log('  ' + data.error, 'err');
    updatePositions(data);
    syncMountedTip(data);
  } catch(e) { log('  Drop failed: ' + e, 'err'); }
  finally {
    busy = false;
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').style.color = '#34d399';
  }
}

async function recordPosition(armName) {
  const label = document.getElementById('teach-label').value.trim();
  if (!label) { log('Enter a label first', 'err'); return; }
  log('> RECORD ' + armName.toUpperCase() + ': ' + label, '');
  try {
    const resp = await fetch('/record', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({label: label, arm: armName})
    });
    const data = await resp.json();
    log(data.message || data.error, data.error ? 'err' : 'ok');
    loadSaved();
  } catch(e) { log('Record failed: ' + e, 'err'); }
}

async function teachLabware() {
  const field = document.getElementById('teach-field').value;
  const labware = document.getElementById('teach-labware').value;
  const tipType = document.getElementById('teach-tip-type').value;
  const ext = TIP_EXT[tipType] || 0;
  const extLabel = ext > 0 ? ' (tip offset: -' + ext + ')' : '';
  log('> TEACH: ' + labware + '.' + field + ' = current Z' + extLabel, '');
  try {
    const resp = await fetch('/teach', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({field: field, labware: labware, tip_type: tipType})
    });
    const data = await resp.json();
    log('  ' + (data.message || data.error), data.error ? 'err' : 'ok');
    loadLabware();  // refresh to show EDITED tag
  } catch(e) { log('  Teach failed: ' + e, 'err'); }
}

async function inlineTeach(labwareName, field) {
  const tipType = getMountedTip();
  const ext = TIP_EXT[tipType] || 0;
  const extLabel = ext > 0 ? ' (tip offset: -' + ext + ')' : '';
  log('> TEACH: ' + labwareName + '.' + field + ' = current Z' + extLabel, '');
  try {
    const resp = await fetch('/teach', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({field: field, labware: labwareName, tip_type: tipType})
    });
    const data = await resp.json();
    log('  ' + (data.message || data.error), data.error ? 'err' : 'ok');
    loadLabware();
  } catch(e) { log('  Teach failed: ' + e, 'err'); }
}

async function undoTeach() {
  log('> UNDO last teach', '');
  try {
    const resp = await fetch('/undo_teach', {method: 'POST'});
    const data = await resp.json();
    log('  ' + (data.message || data.error), data.error ? 'err' : 'ok');
    loadLabware();
  } catch(e) { log('  Undo failed: ' + e, 'err'); }
}

function updatePositions(data) {
  if (data.liha) {
    document.getElementById('liha-x').textContent = (data.liha.x/10).toFixed(1) + ' mm';
    document.getElementById('liha-y').textContent = (data.liha.y/10).toFixed(1) + ' mm';
    document.getElementById('liha-z').textContent = (data.liha.z/10).toFixed(1) + ' mm';
    document.getElementById('liha-x-bar').style.width = Math.min(100, data.liha.x/100) + '%';
    document.getElementById('liha-y-bar').style.width = Math.min(100, data.liha.y/30) + '%';
    document.getElementById('liha-z-bar').style.width = Math.min(100, data.liha.z/21) + '%';
    // Tip offset display
    const tipType = getMountedTip();
    const tipExt = TIP_EXT[tipType] || 0;
    const showTip = tipExt > 0;
    ['liha-ztip-row1','liha-ztip-row2','liha-ztip-row3'].forEach(id =>
      document.getElementById(id).style.display = showTip ? '' : 'none');
    document.getElementById('liha-tip-label').style.display = showTip ? 'block' : 'none';
    if (showTip) {
      const tipZ = data.liha.z - tipExt;
      document.getElementById('liha-ztip').textContent = (tipZ/10).toFixed(1) + ' mm';
      document.getElementById('liha-ztip-bar').style.width = Math.min(100, Math.max(0, tipZ/21)) + '%';
      document.getElementById('liha-tip-label').textContent = tipType + ' (tip extends ' + (tipExt/10).toFixed(1) + 'mm below channel)';
    }
  }
  if (data.roma) {
    document.getElementById('roma-x').textContent = (data.roma.x/10).toFixed(1) + ' mm';
    document.getElementById('roma-y').textContent = (data.roma.y/10).toFixed(1) + ' mm';
    document.getElementById('roma-z').textContent = (data.roma.z/10).toFixed(1) + ' mm';
    document.getElementById('roma-r').textContent = (data.roma.r/10).toFixed(1) + ' deg';
    document.getElementById('roma-x-bar').style.width = Math.min(100, data.roma.x/100) + '%';
    document.getElementById('roma-y-bar').style.width = Math.min(100, data.roma.y/30) + '%';
    document.getElementById('roma-z-bar').style.width = Math.min(100, data.roma.z/26) + '%';
    document.getElementById('roma-r-bar').style.width = Math.min(100, data.roma.r/36) + '%';
    if (data.roma.g !== undefined) {
      document.getElementById('roma-g').textContent = (data.roma.g/10).toFixed(1) + ' mm';
      document.getElementById('roma-g-bar').style.width = Math.min(100, data.roma.g/10) + '%';
    }
  }
  // Update compact readout
  const ro = document.getElementById('pos-readout');
  if (ro) {
    let txt = '';
    if (data.liha) txt += 'LiHa: X=' + (data.liha.x/10).toFixed(1) + '  Y=' + (data.liha.y/10).toFixed(1) + '  Z=' + (data.liha.z/10).toFixed(1);
    if (data.roma) txt += (txt ? '  |  ' : '') + 'RoMa: X=' + (data.roma.x/10).toFixed(1) + '  Y=' + (data.roma.y/10).toFixed(1) + '  Z=' + (data.roma.z/10).toFixed(1);
    ro.textContent = txt || 'No position data';
  }
  updateDeckArm(data);
}

async function pollPositions() {
  if (busy || !isConnected) return;
  try {
    const resp = await fetch('/positions');
    if (busy || !isConnected) return;
    const data = await resp.json();
    if (busy || !isConnected) return;
    updatePositions(data);
  } catch(e) {
    document.getElementById('status').textContent = 'Disconnected';
    document.getElementById('status').style.color = '#60a5fa';
  }
}

async function loadSaved() {
  try {
    const resp = await fetch('/saved');
    const data = await resp.json();
    const list = document.getElementById('saved-list');
    list.innerHTML = '';
    for (const [label, pos] of Object.entries(data)) {
      const div = document.createElement('div');
      div.className = 'saved-pos';
      if (pos.arm === 'roma') {
        div.innerHTML = '<span>' + label + ' <span style="color:#334155;font-size:10px">[RoMa]</span></span>' +
          '<span style="color:#64748b">X=' + pos.x + ' Y=' + pos.y + ' Z=' + pos.z + ' R=' + pos.r + ' G=' + pos.g + '</span>';
      } else {
        div.innerHTML = '<span>' + label + ' <span style="color:#334155;font-size:10px">[LiHa]</span></span>' +
          '<span style="color:#64748b">X=' + pos.x + ' Y=' + pos.y + ' Z1=' + (pos.z ? pos.z[0] : '?') + '</span>';
      }
      list.appendChild(div);
    }
  } catch(e) {}
}

// Keyboard handler
document.addEventListener('keydown', function(e) {
  // Skip jog keys when typing in input fields
  if (e.target.tagName.match(/INPUT|SELECT|TEXTAREA/i)) return;

  // Prevent page scrolling for arrow keys
  if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','PageUp','PageDown','Home','End'].includes(e.key)) {
    e.preventDefault();
  }

  // LiHa numpad
  if (e.key === '4' || e.code === 'Numpad4') { sendJog('liha', 'x', -1); return; }
  if (e.key === '6' || e.code === 'Numpad6') { sendJog('liha', 'x', 1); return; }
  if (e.key === '8' || e.code === 'Numpad8') { sendJog('liha', 'y', -1); return; }  // 8 = back (away from operator)
  if (e.key === '2' || e.code === 'Numpad2') { sendJog('liha', 'y', 1); return; }   // 2 = forward (toward operator)
  if (e.code === 'NumpadAdd' || e.key === '+') {
    sendJog('liha', 'z', -1); return; }  // + = down (toward deck, decrease Z)
  if (e.code === 'NumpadSubtract' || e.key === '-') {
    sendJog('liha', 'z', 1); return; }   // - = up (away from deck, increase Z)
  if (e.key === '7' || e.code === 'Numpad7') {
    stepIdx = Math.max(0, stepIdx - 1); updateStep(); return; }
  if (e.key === '9' || e.code === 'Numpad9') {
    stepIdx = Math.min(STEPS.length - 1, stepIdx + 1); updateStep(); return; }

  // RoMa arrows
  if (e.key === 'ArrowLeft') { sendJog('roma', 'x', -1); return; }
  if (e.key === 'ArrowRight') { sendJog('roma', 'x', 1); return; }
  if (e.key === 'ArrowUp') { sendJog('roma', 'y', 1); return; }
  if (e.key === 'ArrowDown') { sendJog('roma', 'y', -1); return; }
  if (e.key === 'PageUp') { sendJog('roma', 'z', 1); return; }   // up
  if (e.key === 'PageDown') { sendJog('roma', 'z', -1); return; } // down
  if (e.key === 'Home') { sendJog('roma', 'r', -1); return; }
  if (e.key === 'End') { sendJog('roma', 'r', 1); return; }
  if (e.key === '[') { sendJog('roma', 'g', -1); return; }
  if (e.key === ']') { sendJog('roma', 'g', 1); return; }
});

let isConnected = false;

async function toggleConnect() {
  const btn = document.getElementById('btn-connect');
  const status = document.getElementById('status');
  if (isConnected) {
    btn.textContent = 'Disconnecting...';
    btn.disabled = true;
    try {
      const resp = await fetch('/disconnect', {method: 'POST'});
      const data = await resp.json();
      isConnected = data.connected;
    } catch(e) { log('Disconnect failed: ' + e, 'err'); }
  } else {
    btn.textContent = 'Connecting...';
    btn.disabled = true;
    status.textContent = 'Connecting...';
    status.style.color = '#fbbf24';
    log('> Connecting to EVO...', '');
    try {
      const resp = await fetch('/connect', {method: 'POST'});
      const data = await resp.json();
      isConnected = data.connected;
      if (data.message) log('  ' + data.message, 'ok');
      if (data.error) log('  ' + data.error, 'err');
    } catch(e) { log('  Connect failed: ' + e, 'err'); }
  }
  updateConnectButton();
}

function updateConnectButton() {
  const btn = document.getElementById('btn-connect');
  const status = document.getElementById('status');
  btn.disabled = false;
  if (isConnected) {
    btn.textContent = 'Disconnect';
    btn.style.background = '#60a5fa';
    status.textContent = 'Connected';
    status.style.color = '#34d399';
  } else {
    btn.textContent = 'Connect';
    btn.style.background = '#334155';
    status.textContent = 'Disconnected';
    status.style.color = '#64748b';
  }
}

let labwareData = {};

const TEACH_ITEMS = {
  'TecanPlate': [
    {field: 'z_start', tip: true, label: 'z_start', desc: 'Just above plate top'},
    {field: 'z_dispense', tip: true, label: 'z_dispense', desc: 'Dispense height inside well'},
    {field: 'z_max', tip: true, label: 'z_max', desc: 'Max safe depth (near well bottom)'},
  ],
  'TecanTipRack': [
    {field: 'z_start', tip: false, label: 'z_start', desc: 'Just above tip tops (bare channel)'},
    {field: 'z_max', tip: false, label: 'z_max', desc: 'Bottom of tip search range (bare channel)'},
  ],
};

function buildTeachChecklist() {
  const el = document.getElementById('teach-checklist');
  if (!el || !labwareData) return;
  let html = '';
  for (const [name, lw] of Object.entries(labwareData)) {
    const items = TEACH_ITEMS[lw.type];
    if (!items) continue;
    html += '<div style="margin-bottom:8px;padding:6px;background:#1e293b;border-radius:4px;border:1px solid #334155;">';
    html += '<div style="color:#60a5fa;font-weight:bold;margin-bottom:4px;">' + name + ' <span style="color:#334155;font-weight:normal">(' + lw.model + ')</span></div>';
    for (const item of items) {
      const val = lw[item.field];
      const edited = lw['edited_' + item.field];
      const hasDefault = val !== undefined && val !== null;
      let statusIcon, statusColor;
      if (edited) {
        statusIcon = '✓';
        statusColor = '#34d399';
      } else if (hasDefault) {
        statusIcon = '~';
        statusColor = '#fbbf24';
      } else {
        statusIcon = '✗';
        statusColor = '#60a5fa';
      }
      const valStr = hasDefault ? val + ' (' + (val/10).toFixed(1) + 'mm)' : 'not set';
      const tipNote = item.tip ? ' [tips mounted]' : ' [bare channel]';
      html += '<div style="display:flex;align-items:center;gap:6px;padding:2px 0;">';
      html += '<span style="color:' + statusColor + ';width:14px;text-align:center;">' + statusIcon + '</span>';
      html += '<button class="btn small" style="padding:2px 6px;font-size:10px;" ';
      html += 'onclick="setupTeach(\\\'' + name + '\\\',\\\'' + item.field + '\\\',' + item.tip + ')">';
      html += item.label + '</button>';
      html += '<span style="color:#64748b;">' + item.desc + tipNote + '</span>';
      html += '<span style="color:#cbd5e1;margin-left:auto;">' + valStr + '</span>';
      if (edited) html += '<span style="color:#fbbf24;margin-left:4px;">TAUGHT</span>';
      if (hasDefault) {
        html += '<button class="btn small" style="padding:1px 6px;font-size:10px;margin-left:4px;border-color:#34d399;color:#34d399;" ';
        html += 'onclick="goToTeachPoint(\\\'' + name + '\\\',\\\'' + item.field + '\\\')">Go</button>';
      }
      html += '<button class="btn small" style="padding:1px 6px;font-size:10px;margin-left:2px;border-color:#fbbf24;color:#fbbf24;" ';
      html += 'onclick="inlineTeach(\\\'' + name + '\\\',\\\'' + item.field + '\\\')">Set</button>';
      html += '</div>';
    }
    html += '</div>';
  }
  if (!html) html = '<div style="color:#334155">No labware on deck</div>';
  el.innerHTML = html;
}

function getMountedTip() { return document.getElementById('teach-tip-type').value; }

async function goToTeachPoint(labwareName, field) {
  // Auto-select this as the active teach point
  document.getElementById('teach-labware').value = labwareName;
  document.getElementById('teach-field').value = field;
  showLabware(labwareName);

  if (!isConnected) { log('Not connected', 'err'); return; }
  if (busy) { log('Busy — wait for current operation', 'err'); return; }
  busy = true;
  document.getElementById('status').textContent = 'Moving...';
  document.getElementById('status').style.color = '#fbbf24';
  const tipType = getMountedTip();
  const tipLabel = tipType !== 'none' ? ' [' + tipType + ' tips]' : ' [bare]';

  if (gotoMode === 'z') {
    log('> GO TO (Z): ' + labwareName + '.' + field + tipLabel, '');
    try {
      const resp = await fetch('/goto', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({labware: labwareName, field: field, mode: 'z', tip_type: tipType})
      });
      const data = await resp.json();
      if (data.error) { log('  ' + data.error, 'err'); }
      else {
        if (data.message) log('  ' + data.message, 'ok');
        updatePositions(data);
      }
    } catch(e) { log('  Go To failed: ' + e, 'err'); }
    finally {
      busy = false;
      document.getElementById('status').textContent = 'Connected';
      document.getElementById('status').style.color = '#34d399';
    }
  } else {
    log('> GO TO (XYZ): ' + labwareName + '.' + field + tipLabel + ' — raising Z...', '');
    try {
      const resp = await fetch('/goto', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({labware: labwareName, field: field, mode: 'xyz', confirm: false, tip_type: tipType})
      });
      const data = await resp.json();
      if (data.error) { log('  ' + data.error, 'err'); busy = false; return; }
      updatePositions(data);
      log('  Z raised. Target: X=' + (data.target_x/10).toFixed(1) + ' Y=' + (data.target_y/10).toFixed(1) + ' Z=' + (data.target_z/10).toFixed(1), '');
      pendingGoto = {labware: labwareName, field: field, target_x: data.target_x, target_y: data.target_y, target_z: data.target_z, tip_type: tipType};
      document.getElementById('confirm-msg').textContent = 'Move LiHa to ' + labwareName + '?';
      document.getElementById('confirm-coords').textContent = 'X=' + (data.target_x/10).toFixed(1) + '  Y=' + (data.target_y/10).toFixed(1) + '  Z=' + (data.target_z/10).toFixed(1);
      document.getElementById('confirm-modal').classList.add('visible');
    } catch(e) {
      log('  Go To failed: ' + e, 'err');
      busy = false;
      document.getElementById('status').textContent = 'Connected';
      document.getElementById('status').style.color = '#34d399';
    }
  }
}

async function confirmGoto() {
  const modal = document.getElementById('confirm-modal');
  modal.classList.remove('visible');
  if (!pendingGoto) { busy = false; return; }
  log('  Confirmed — moving X/Y/Z...', 'ok');
  try {
    const resp = await fetch('/goto', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({labware: pendingGoto.labware, field: pendingGoto.field, mode: 'xyz', confirm: true, tip_type: pendingGoto.tip_type})
    });
    const data = await resp.json();
    if (data.error) { log('  ' + data.error, 'err'); }
    else {
      if (data.message) log('  ' + data.message, 'ok');
      updatePositions(data);
    }
  } catch(e) { log('  Move failed: ' + e, 'err'); }
  finally {
    pendingGoto = null;
    busy = false;
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').style.color = '#34d399';
  }
}

function cancelGoto() {
  document.getElementById('confirm-modal').classList.remove('visible');
  log('  XY move cancelled — Z remains raised', 'err');
  pendingGoto = null;
  busy = false;
  document.getElementById('status').textContent = 'Connected';
  document.getElementById('status').style.color = '#34d399';
}

document.addEventListener('keydown', function(e) {
  if (document.getElementById('confirm-modal').classList.contains('visible')) {
    if (e.key === 'Enter') { e.preventDefault(); confirmGoto(); }
    if (e.key === 'Escape') { e.preventDefault(); cancelGoto(); }
  }
});

function setupTeach(labwareName, field, needsTips) {
  document.getElementById('teach-labware').value = labwareName;
  document.getElementById('teach-field').value = field;
  showLabware(labwareName);
  const tipMsg = needsTips ? ' (mount tips first!)' : ' (bare channel)';
  log('> Ready to teach: ' + labwareName + '.' + field + tipMsg, 'ok');
  log('  Jog to position, then click SET or press Enter', '');
}

async function loadLabware() {
  try {
    const resp = await fetch('/labware');
    labwareData = await resp.json();
    const tabs = document.getElementById('labware-tabs');
    const select = document.getElementById('teach-labware');
    tabs.innerHTML = '';
    select.innerHTML = '';
    for (const name of Object.keys(labwareData)) {
      const btn = document.createElement('button');
      btn.className = 'btn small';
      btn.textContent = name;
      btn.onclick = () => showLabware(name);
      tabs.appendChild(btn);
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    }
    // Show first by default
    const first = Object.keys(labwareData)[0];
    if (first) showLabware(first);
    buildTeachChecklist();
    renderDeckMap();
  } catch(e) { log('Failed to load labware: ' + e, 'err'); }
}

const DECK_W = 1315, DECK_H = 400;
const DECK_SCALE = 960 / DECK_W;
const DECK_COLORS = { TecanPlate: '#60a5fa', TecanTipRack: '#34d399' };

function renderDeckMap() {
  const g = document.getElementById('deck-labware');
  if (!g) return;
  g.innerHTML = '';
  for (const [name, lw] of Object.entries(labwareData)) {
    const sx = lw.loc_x * DECK_SCALE;
    const sy = (DECK_H - lw.loc_y - lw.size_y) * DECK_SCALE;
    const sw = lw.size_x * DECK_SCALE;
    const sh = lw.size_y * DECK_SCALE;
    const color = DECK_COLORS[lw.type] || '#334155';
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('class', 'lw-rect');
    rect.setAttribute('x', sx);
    rect.setAttribute('y', sy);
    rect.setAttribute('width', sw);
    rect.setAttribute('height', sh);
    rect.setAttribute('fill', color);
    rect.setAttribute('rx', '3');
    rect.onclick = function() { showLabware(name); };
    g.appendChild(rect);
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('class', 'lw-label');
    label.setAttribute('x', sx + sw / 2);
    label.setAttribute('y', sy + sh / 2 + 3);
    label.setAttribute('text-anchor', 'middle');
    label.textContent = name.replace('_r', ' R').replace('tips_', 'T');
    g.appendChild(label);
  }
}

function updateDeckArm(data) {
  const g = document.getElementById('deck-arm');
  if (!g) return;
  g.innerHTML = '';
  function drawMarker(pos, color, label, yOff) {
    if (!pos) return;
    const px = ((pos.x / 10 + 100) * DECK_SCALE);
    const py = ((DECK_H - (346.5 - pos.y / 10)) * DECK_SCALE);
    const cross = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    cross.innerHTML =
      '<line x1="' + (px-6) + '" y1="' + py + '" x2="' + (px+6) + '" y2="' + py + '" stroke="' + color + '" stroke-width="2"/>' +
      '<line x1="' + px + '" y1="' + (py-6) + '" x2="' + px + '" y2="' + (py+6) + '" stroke="' + color + '" stroke-width="2"/>' +
      '<circle cx="' + px + '" cy="' + py + '" r="3" fill="' + color + '" opacity="0.6"/>' +
      '<text x="' + (px+8) + '" y="' + (py + (yOff||0)) + '" fill="' + color + '" font-size="8" font-family="sans-serif">' + label + '</text>';
    g.appendChild(cross);
  }
  drawMarker(data.liha, '#f87171', 'LiHa', -2);
  drawMarker(data.roma, '#5eead4', 'RoMa', 10);
}

function deckClick(e) {
  if (!isConnected || busy) return;
  const svg = document.getElementById('deck-svg');
  const pt = svg.createSVGPoint();
  pt.x = e.clientX;
  pt.y = e.clientY;
  const svgPt = pt.matrixTransform(svg.getScreenCTM().inverse());
  const plr_x = svgPt.x / DECK_SCALE;
  const plr_y = DECK_H - svgPt.y / DECK_SCALE;
  const tecan_x = Math.round((plr_x - 100) * 10);
  const tecan_y = Math.round((346.5 - plr_y) * 10);
  if (tecan_x < 0 || tecan_y < 0) return;
  log('> MOVE XY: X=' + (tecan_x/10).toFixed(1) + ' Y=' + (tecan_y/10).toFixed(1), '');
  moveXY(tecan_x, tecan_y);
}

async function moveXY(tx, ty) {
  busy = true;
  document.getElementById('status').textContent = 'Moving...';
  document.getElementById('status').style.color = '#fbbf24';
  try {
    const resp = await fetch('/move_xy', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({x: tx, y: ty})
    });
    const data = await resp.json();
    if (data.error) { log('  ' + data.error, 'err'); }
    else {
      if (data.message) log('  ' + data.message, 'ok');
      updatePositions(data);
    }
  } catch(e) { log('  Move failed: ' + e, 'err'); }
  finally {
    busy = false;
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').style.color = '#34d399';
  }
}

async function directMove() {
  if (!isConnected) { log('Not connected', 'err'); return; }
  if (busy) { log('Busy — wait for current operation', 'err'); return; }
  const xEl = document.getElementById('input-x');
  const yEl = document.getElementById('input-y');
  const zEl = document.getElementById('input-z');
  const xMm = parseFloat(xEl.value);
  const yMm = parseFloat(yEl.value);
  const zMm = parseFloat(zEl.value);
  const hasX = !isNaN(xMm);
  const hasY = !isNaN(yMm);
  const hasZ = !isNaN(zMm);
  if (!hasX && !hasY && !hasZ) { log('Enter at least one coordinate', 'err'); return; }
  const tipType = getMountedTip();
  const tipExt = TIP_EXT[tipType] || 0;
  const parts = [];
  if (hasX) parts.push('X=' + xMm.toFixed(1));
  if (hasY) parts.push('Y=' + yMm.toFixed(1));
  if (hasZ) parts.push('Z=' + zMm.toFixed(1) + (tipExt ? ' tip end' : ''));
  if (tipExt) parts.push('[' + tipType + ']');
  log('> DIRECT MOVE: ' + parts.join(' '), '');
  busy = true;
  document.getElementById('status').textContent = 'Moving...';
  document.getElementById('status').style.color = '#fbbf24';
  try {
    const resp = await fetch('/direct_move', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        x: hasX ? Math.round(xMm * 10) : null,
        y: hasY ? Math.round(yMm * 10) : null,
        z: hasZ ? Math.round(zMm * 10) : null,
        tip_type: tipType
      })
    });
    const data = await resp.json();
    if (data.error) { log('  ' + data.error, 'err'); }
    else {
      if (data.message) log('  ' + data.message, 'ok');
      updatePositions(data);
    }
  } catch(e) { log('  Direct move failed: ' + e, 'err'); }
  finally {
    busy = false;
    document.getElementById('status').textContent = 'Connected';
    document.getElementById('status').style.color = '#34d399';
  }
}

document.getElementById('deck-svg').addEventListener('click', deckClick);

function showLabware(name) {
  const lw = labwareData[name];
  if (!lw) return;
  // Highlight active tab
  document.querySelectorAll('#labware-tabs .btn').forEach(b => {
    b.className = 'btn small' + (b.textContent === name ? ' active' : '');
  });
  // Also set the teach dropdown
  document.getElementById('teach-labware').value = name;

  let html = '<div style="margin-bottom:8px">';
  html += '<b style="color:#60a5fa;font-size:13px">' + name + '</b>';
  html += '<span style="color:#334155;margin-left:8px">' + lw.type + '</span>';
  html += '</div>';
  html += '<div style="color:#64748b;margin-bottom:6px">' + lw.model + '</div>';
  html += '<table style="width:100%;font-family:monospace;font-size:11px;border-collapse:collapse">';

  const rows = [
    ['Size', lw.size_x + ' x ' + lw.size_y + ' x ' + lw.size_z + ' mm'],
    ['Location (PLR)', 'x=' + lw.loc_x + '  y=' + lw.loc_y + '  z=' + lw.loc_z + ' mm'],
    ['Tecan center', 'X=' + (lw.tecan_x/10).toFixed(1) + '  Y=' + (lw.tecan_y/10).toFixed(1) + ' mm'],
  ];
  if (lw.z_start !== undefined) rows.push(['z_start', lw.z_start + ' (' + (lw.z_start/10).toFixed(1) + 'mm)' + (lw.edited_z_start ? ' <span style="color:#fbbf24">EDITED</span>' : '')]);
  if (lw.z_dispense !== undefined) rows.push(['z_dispense', lw.z_dispense + ' (' + (lw.z_dispense/10).toFixed(1) + 'mm)' + (lw.edited_z_dispense ? ' <span style="color:#fbbf24">EDITED</span>' : '')]);
  if (lw.z_max !== undefined) rows.push(['z_max', lw.z_max + ' (' + (lw.z_max/10).toFixed(1) + 'mm)' + (lw.edited_z_max ? ' <span style="color:#fbbf24">EDITED</span>' : '')]);
  if (lw.area !== undefined) rows.push(['area', lw.area + ' mm²']);
  if (lw.item_dy !== undefined) rows.push(['well pitch', lw.item_dy + ' mm']);
  if (lw.num_items !== undefined) rows.push(['wells/tips', lw.num_items + ' (' + lw.num_items_x + 'x' + lw.num_items_y + ')']);
  if (lw.tip_length !== undefined) rows.push(['tip length', lw.tip_length + ' mm']);
  if (lw.tip_type !== undefined) rows.push(['tip type', lw.tip_type]);

  for (const [label, val] of rows) {
    html += '<tr><td style="padding:2px 8px 2px 0;color:#cbd5e1;white-space:nowrap">' + label + '</td>';
    html += '<td style="padding:2px 0">' + val + '</td></tr>';
  }
  html += '</table>';
  document.getElementById('labware-detail').innerHTML = html;
}

// Start polling
polling = setInterval(pollPositions, 1000);
try {
  pollPositions();
  loadSaved();
  loadLabware();
} catch(e) {
  console.error('Init error:', e);
  log('INIT ERROR: ' + e.message, 'err');
}
</script>
</body>
</html>
"""


import threading

_usb_lock = threading.Lock()


@app.route("/")
def index():
  return render_template_string(HTML)


@app.route("/positions")
def positions():
  if not connected:
    return jsonify({})
  if not _usb_lock.acquire(blocking=False):
    return jsonify({})
  try:
    liha_pos = run_async(get_liha_position())
    roma_pos = run_async(get_roma_position())
    return jsonify({"liha": liha_pos, "roma": roma_pos})
  except Exception as e:
    return jsonify({"error": str(e)})
  finally:
    _usb_lock.release()


@app.route("/jog", methods=["POST"])
def jog():
  data = request.json
  arm_name = data["arm"]
  axis = data["axis"]
  direction = data["direction"]
  step_mm = data["step"]
  delta = int(step_mm * 10 * direction)

  module = "C5" if arm_name == "liha" else "C1"
  cmd_map = {"x": "PRX", "y": "PRY", "z": "PRZ", "r": "PRR"}
  cmd_name = f"{module} {cmd_map.get(axis, '?')}{delta}"

  with _usb_lock:
    try:
      run_async(do_jog(arm_name, axis, delta))
      liha_pos = run_async(get_liha_position())
      roma_pos = run_async(get_roma_position())
      return jsonify({"liha": liha_pos, "roma": roma_pos, "cmd": cmd_name})
    except Exception as e:
      return jsonify({"error": str(e), "cmd": cmd_name})


@app.route("/record", methods=["POST"])
def record():
  data = request.json
  label = data["label"]
  arm_name = data.get("arm", "liha")
  with _usb_lock:
    try:
      saved = load_json_file(POSITIONS_FILE)
      if arm_name == "roma":
        pos = run_async(get_roma_position())
        saved[label] = {"arm": "roma", "x": pos["x"], "y": pos["y"], "z": pos["z"], "r": pos["r"], "g": pos["g"]}
        save_json_file(POSITIONS_FILE, saved)
        return jsonify({"message": f"Recorded RoMa '{label}': X={pos['x']} Y={pos['y']} Z={pos['z']} R={pos['r']} G={pos['g']}"})
      else:
        pos = run_async(get_liha_position())
        saved[label] = {"x": pos["x"], "y": pos["y"], "z": pos["z_all"]}
        save_json_file(POSITIONS_FILE, saved)
        return jsonify({"message": f"Recorded LiHa '{label}': X={pos['x']} Y={pos['y']} Z1={pos['z']}"})
    except Exception as e:
      return jsonify({"error": str(e)})


last_teach_undo = None


@app.route("/teach", methods=["POST"])
def teach():
  global last_teach_undo
  from labware_library import TIP_TYPES

  data = request.json
  field = data["field"]
  labware_name = data["labware"]
  tip_type = data.get("tip_type", "none")
  tip_ext = TIP_TYPES.get(tip_type, {}).get("tip_ext", 0)

  with _usb_lock:
    try:
      pos = run_async(get_liha_position())
      raw_z = pos["z"]
      z_val = raw_z - tip_ext
      edits = load_json_file(LABWARE_FILE)
      old_val = edits.get(labware_name, {}).get(field)
      if labware_name not in edits:
        edits[labware_name] = {}
      edits[labware_name][field] = z_val
      save_json_file(LABWARE_FILE, edits)
      last_teach_undo = {"labware": labware_name, "field": field, "old_val": old_val, "new_val": z_val}
      tip_msg = f" (raw={raw_z} - tip_ext={tip_ext})" if tip_ext > 0 else ""
      return jsonify({"message": f"{labware_name}.{field} = {z_val} ({z_val / 10:.1f}mm){tip_msg}"})
    except Exception as e:
      return jsonify({"error": str(e)})


@app.route("/undo_teach", methods=["POST"])
def undo_teach():
  global last_teach_undo
  if last_teach_undo is None:
    return jsonify({"error": "Nothing to undo"})
  lw = last_teach_undo["labware"]
  field = last_teach_undo["field"]
  old_val = last_teach_undo["old_val"]
  new_val = last_teach_undo["new_val"]
  edits = load_json_file(LABWARE_FILE)
  if old_val is None:
    if lw in edits and field in edits[lw]:
      del edits[lw][field]
      if not edits[lw]:
        del edits[lw]
  else:
    if lw not in edits:
      edits[lw] = {}
    edits[lw][field] = old_val
  save_json_file(LABWARE_FILE, edits)
  old_str = f"{old_val} ({old_val / 10:.1f}mm)" if old_val is not None else "default"
  msg = f"Undo: {lw}.{field} reverted from {new_val} to {old_str}"
  last_teach_undo = None
  return jsonify({"message": msg})


TIP_TYPE_MAP = {"50": "50ul", "200": "200ul", "1000": "1000ul"}


@app.route("/action", methods=["POST"])
def action():
  data = request.json
  act = data["action"]
  with _usb_lock:
    try:
      result = run_async(do_action(act, data))
      liha_pos = run_async(get_liha_position())
      roma_pos = run_async(get_roma_position())
      resp_data = {"message": result, "liha": liha_pos, "roma": roma_pos}
      if act == "pick_up_tips":
        resp_data["mounted_tip"] = TIP_TYPE_MAP.get(data.get("tip_type", ""), "none")
      elif act in ("drop_tips", "eject_tips"):
        resp_data["mounted_tip"] = "none"
      return jsonify(resp_data)
    except Exception as e:
      return jsonify({"error": str(e)})


@app.route("/goto", methods=["POST"])
def goto():
  data = request.json
  labware_name = data["labware"]
  field = data["field"]
  mode = data.get("mode", "z")
  confirm = data.get("confirm", False)
  with _usb_lock:
    try:
      tip_type = data.get("tip_type", "none")
      result = run_async(do_goto(labware_name, field, mode, confirm, tip_type))
      liha_pos = run_async(get_liha_position())
      roma_pos = run_async(get_roma_position())
      result["liha"] = liha_pos
      result["roma"] = roma_pos
      return jsonify(result)
    except Exception as e:
      return jsonify({"error": str(e)})


@app.route("/direct_move", methods=["POST"])
def direct_move():
  from labware_library import TIP_TYPES
  data = request.json
  tx = data.get("x")
  ty = data.get("y")
  tz = data.get("z")
  tip_type = data.get("tip_type", "none")
  tip_ext = TIP_TYPES.get(tip_type, {}).get("tip_ext", 0)
  with _usb_lock:
    try:
      pip_be = evo.pip.backend
      z_range = pip_be._z_range
      num_ch = pip_be.num_channels
      # Safe sequence: raise Z first if X or Y is changing
      if tx is not None or ty is not None:
        z_params = ",".join([str(z_range)] * num_ch)
        run_async(driver.send_command("C5", command=f"PAZ{z_params}"))
      if tx is not None:
        run_async(driver.send_command("C5", command=f"PAX{tx}"))
      if ty is not None:
        run_async(driver.send_command("C5", command=f"PAY{ty}"))
      if tz is not None:
        # Z input = desired tip-end position; offset by tip extension
        channel_z = tz + tip_ext
        channel_z = min(channel_z, z_range)
        z_params = ",".join([str(channel_z)] * num_ch)
        run_async(driver.send_command("C5", command=f"PAZ{z_params}"))
      liha_pos = run_async(get_liha_position())
      roma_pos = run_async(get_roma_position())
      parts = []
      if tx is not None: parts.append(f"X={tx / 10:.1f}")
      if ty is not None: parts.append(f"Y={ty / 10:.1f}")
      if tz is not None:
        tip_msg = f" +tip({tip_ext})" if tip_ext else ""
        parts.append(f"Z={tz / 10:.1f} tip end{tip_msg}")
      return jsonify({
        "message": f"Moved to {' '.join(parts)}",
        "liha": liha_pos,
        "roma": roma_pos,
      })
    except Exception as e:
      return jsonify({"error": str(e)})


@app.route("/move_xy", methods=["POST"])
def move_xy():
  data = request.json
  tx = data["x"]
  ty = data["y"]
  with _usb_lock:
    try:
      pip_be = evo.pip.backend
      z_range = pip_be._z_range
      num_ch = pip_be.num_channels
      z_params = ",".join([str(z_range)] * num_ch)
      run_async(driver.send_command("C5", command=f"PAZ{z_params}"))
      run_async(driver.send_command("C5", command=f"PAX{tx}"))
      run_async(driver.send_command("C5", command=f"PAY{ty}"))
      liha_pos = run_async(get_liha_position())
      roma_pos = run_async(get_roma_position())
      return jsonify({
        "message": f"Moved to X={tx / 10:.1f} Y={ty / 10:.1f} (Z raised)",
        "liha": liha_pos,
        "roma": roma_pos,
      })
    except Exception as e:
      return jsonify({"error": str(e)})


@app.route("/saved")
def saved():
  return jsonify(load_json_file(POSITIONS_FILE))


@app.route("/labware")
def labware_info():
  """Return all labware properties for the UI."""
  edits = load_json_file(LABWARE_FILE)
  result = {}

  def describe_resource(res, deck_ref, edits):
    """Build info dict for a single labware resource."""
    loc = res.get_location_wrt(deck_ref)
    # Tecan-native coordinates for center of labware
    center_x = loc.x + res.get_size_x() / 2
    center_y = loc.y + res.get_size_y() / 2
    tecan_x = round((center_x - 100) * 10, 1)
    tecan_y = round((346.5 - center_y) * 10, 1)
    info = {
      "type": type(res).__name__,
      "model": getattr(res, "model", ""),
      "size_x": round(res.get_size_x(), 1),
      "size_y": round(res.get_size_y(), 1),
      "size_z": round(res.get_size_z(), 1),
      "loc_x": round(loc.x, 1),
      "loc_y": round(loc.y, 1),
      "loc_z": round(loc.z, 1),
      "tecan_x": tecan_x,
      "tecan_y": tecan_y,
    }
    for attr in ("z_start", "z_dispense", "z_max", "area"):
      if hasattr(res, attr):
        val = getattr(res, attr)
        info[attr] = val
        if res.name in edits and attr in edits[res.name]:
          info[attr] = edits[res.name][attr]
          info[f"edited_{attr}"] = True
    if hasattr(res, "num_items"):
      info["num_items"] = res.num_items
    if hasattr(res, "num_items_x"):
      info["num_items_x"] = res.num_items_x
    if hasattr(res, "num_items_y"):
      info["num_items_y"] = res.num_items_y
    if hasattr(res, "item_dy"):
      info["item_dy"] = round(res.item_dy, 2)
    if hasattr(res, "get_tip"):
      try:
        tip = res.get_tip("A1")
        info["tip_length"] = tip.total_tip_length
        if hasattr(tip, "tip_type"):
          info["tip_type"] = str(tip.tip_type.value)
      except Exception:
        pass
    return info

  def find_labware(resource, deck_ref, edits):
    """Recursively find labware (TecanPlate, TecanTipRack) in resource tree."""
    items = {}
    for child in resource.children:
      ctype = type(child).__name__
      # If it's a plate or tip rack, add it
      if ctype in ("TecanPlate", "TecanTipRack"):
        items[child.name] = describe_resource(child, deck_ref, edits)
      # Recurse into children
      items.update(find_labware(child, deck_ref, edits))
    return items

  if evo is not None:
    deck_ref = evo.children[0] if evo.children else evo
    unsorted = find_labware(deck_ref, deck_ref, edits)
    result = dict(sorted(unsorted.items(), key=lambda kv: (kv[1]["loc_x"], kv[1]["loc_y"])))

  return jsonify(result)


# ============== Async helpers ==============


async def get_liha_position():
  resp_x = await driver.send_command("C5", command="RPX0")
  resp_y = await driver.send_command("C5", command="RPY0")
  resp_z = await driver.send_command("C5", command="RPZ0")
  x = resp_x["data"][0] if resp_x and resp_x.get("data") else 0
  y_data = resp_y["data"] if resp_y and resp_y.get("data") else [0]
  y = y_data[0] if isinstance(y_data, list) else y_data
  z_vals = resp_z["data"] if resp_z and resp_z.get("data") else [0] * 8
  return {"x": x, "y": y, "z": z_vals[0], "z_all": z_vals}


async def get_roma_position():
  try:
    resp_x = await driver.send_command("C1", command="RPX0")
    resp_y = await driver.send_command("C1", command="RPY0")
    resp_z = await driver.send_command("C1", command="RPZ0")
    resp_r = await driver.send_command("C1", command="RPR0")
    resp_g = await driver.send_command("C1", command="RPG0")
    return {
      "x": resp_x["data"][0] if resp_x and resp_x.get("data") else 0,
      "y": resp_y["data"][0] if resp_y and resp_y.get("data") else 0,
      "z": resp_z["data"][0] if resp_z and resp_z.get("data") else 0,
      "r": resp_r["data"][0] if resp_r and resp_r.get("data") else 0,
      "g": resp_g["data"][0] if resp_g and resp_g.get("data") else 0,
    }
  except Exception:
    return {"x": 0, "y": 0, "z": 0, "r": 0, "g": 0}


async def do_jog(arm_name, axis, delta):
  if arm_name == "liha":
    module = "C5"
    if axis == "x":
      await driver.send_command(module, command=f"PRX{delta}")
    elif axis == "y":
      await driver.send_command(module, command=f"PRY{delta}")
    elif axis == "z":
      num_ch = evo.pip.num_channels
      z_params = ",".join([str(delta)] * num_ch)
      await driver.send_command(module, command=f"PRZ{z_params}")
  elif arm_name == "roma":
    module = "C1"
    if axis == "x":
      await driver.send_command(module, command=f"PRX{delta}")
    elif axis == "y":
      await driver.send_command(module, command=f"PRY{delta}")
    elif axis == "z":
      await driver.send_command(module, command=f"PRZ{delta}")
    elif axis == "r":
      await driver.send_command(module, command=f"PRR{delta}")
    elif axis == "g":
      await driver.send_command(module, command=f"PRG{delta}")


ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"]


def find_labware_resource(name):
  """Find a labware resource by name in the deck tree."""
  def _search(resource):
    for child in resource.children:
      if child.name == name:
        return child
      found = _search(child)
      if found:
        return found
    return None
  deck = evo.children[0] if evo.children else evo
  return _search(deck), deck


async def do_goto(labware_name, field, mode, confirm, tip_type="none"):
  from labware_library import TIP_TYPES
  res, deck_ref = find_labware_resource(labware_name)
  if res is None:
    return {"error": f"Labware '{labware_name}' not found"}

  edits = load_json_file(LABWARE_FILE)
  if labware_name in edits and field in edits[labware_name]:
    z_val = edits[labware_name][field]
  elif hasattr(res, field):
    z_val = getattr(res, field)
  else:
    return {"error": f"{labware_name} has no {field}"}

  pip_be = evo.pip.backend
  z_range = pip_be._z_range
  num_ch = pip_be.num_channels
  tip_ext = TIP_TYPES.get(tip_type, {}).get("tip_ext", 0)

  # PLR → Tecan XY transform (matches pip_backend.py lines 182-183)
  loc = res.get_location_wrt(deck_ref)
  if hasattr(res, "get_item"):
    try:
      well = res.get_item("A1")
      well_loc = well.get_location_wrt(deck_ref) + well.center()
      ref_x = well_loc.x
      ref_y = well_loc.y
    except Exception:
      ref_x = loc.x + res.get_size_x() / 2
      ref_y = loc.y + res.get_size_y() / 2
  else:
    ref_x = loc.x + res.get_size_x() / 2
    ref_y = loc.y + res.get_size_y() / 2
  target_x = int((ref_x - 100) * 10)
  target_y = int((346.5 - ref_y) * 10)

  # Z: bare-channel position + tip extension offset (tips make the arm longer)
  target_z = int(z_val) + tip_ext
  target_z = min(target_z, z_range)
  tip_msg = f" +tip({tip_ext})" if tip_ext > 0 else ""

  if mode == "z":
    z_params = ",".join([str(target_z)] * num_ch)
    await driver.send_command("C5", command=f"PAZ{z_params}")
    return {"message": f"Z={target_z} ({target_z / 10:.1f}mm){tip_msg} for {labware_name}.{field}"}

  # XYZ mode
  if not confirm:
    z_params = ",".join([str(z_range)] * num_ch)
    await driver.send_command("C5", command=f"PAZ{z_params}")
    return {
      "message": f"Z raised to {z_range}",
      "confirm_needed": True,
      "target_x": target_x,
      "target_y": target_y,
      "target_z": target_z,
    }
  else:
    await driver.send_command("C5", command=f"PAX{target_x}")
    await driver.send_command("C5", command=f"PAY{target_y}")
    z_params = ",".join([str(target_z)] * num_ch)
    await driver.send_command("C5", command=f"PAZ{z_params}")
    return {"message": f"Moved to {labware_name}: X={target_x / 10:.1f} Y={target_y / 10:.1f} Z={target_z / 10:.1f}{tip_msg}"}


async def sync_tip_state():
  """Sync PLR's head tip tracking with hardware RTS."""
  resp = await driver.send_command("C5", command="RTS")
  hw_status = resp["data"][0] if resp and resp.get("data") else 0
  num_ch = evo.pip.num_channels
  for ch in range(num_ch):
    hw_has = bool(hw_status & (1 << ch))
    plr_has = evo.pip.head[ch].has_tip
    if plr_has and not hw_has:
      evo.pip.head[ch].remove_tip()
    # Note: we can't add tips to PLR if we don't know what type — only clear stale state


async def do_action(action, data=None):
  if action == "pick_up_tips":
    tip_type = data.get("tip_type", "200")
    col = data.get("column", 1)
    if tip_type not in tip_racks:
      return f"Unknown tip type: {tip_type}. Choose 50, 200, or 1000."
    await sync_tip_state()
    rack = tip_racks[tip_type]
    wells = [f"{row}{col}" for row in ROWS]
    await evo.pip.pick_up_tips(rack.get_items(wells))
    pip_be = evo.pip.backend
    z_range = pip_be._z_range
    num_ch = pip_be.num_channels
    z_params = ",".join([str(z_range)] * num_ch)
    await driver.send_command("C5", command=f"PAZ{z_params}")
    resp = await driver.send_command("C5", command="RTS")
    status = resp["data"][0] if resp and resp.get("data") else "?"
    return f"Picked up {tip_type}uL tips from col {col} (RTS={status})"
  elif action == "drop_tips":
    tip_type = data.get("tip_type", "200")
    col = data.get("column", 1)
    if tip_type not in tip_racks:
      return f"Unknown tip type: {tip_type}. Choose 50, 200, or 1000."
    await sync_tip_state()
    rack = tip_racks[tip_type]
    wells = [f"{row}{col}" for row in ROWS]
    await evo.pip.drop_tips(rack.get_items(wells))
    pip_be = evo.pip.backend
    z_range = pip_be._z_range
    num_ch = pip_be.num_channels
    z_params = ",".join([str(z_range)] * num_ch)
    await driver.send_command("C5", command=f"PAZ{z_params}")
    return f"Dropped {tip_type}uL tips into col {col}"
  elif action == "home":
    pip_be = evo.pip.backend
    z_range = pip_be._z_range
    num_ch = pip_be.num_channels
    await pip_be.liha.set_z_travel_height([z_range] * num_ch)
    await pip_be.liha.position_absolute_all_axis(45, 1031, 90, [z_range] * num_ch)
    return "LiHa homed"
  elif action == "z_up":
    pip_be = evo.pip.backend
    z_range = pip_be._z_range
    num_ch = pip_be.num_channels
    z_params = ",".join([str(z_range)] * num_ch)
    await driver.send_command("C5", command=f"PAZ{z_params}")
    return f"All channels raised to Z={z_range}"
  elif action == "park_roma":
    if evo.arm and evo.arm.backend.roma:
      await evo.arm.backend.park()
      return "RoMa parked"
    return "RoMa not available"
  elif action == "tips_status":
    resp = await driver.send_command("C5", command="RTS")
    status = resp["data"][0] if resp and resp.get("data") else "?"
    return f"Tip status: {status} (0=none, 255=all)"
  elif action == "eject_tips":
    pip_be = evo.pip.backend
    num_ch = pip_be.num_channels
    z_range = pip_be._z_range
    await pip_be.liha.set_z_travel_height([z_range] * num_ch)
    tips_mask = (1 << num_ch) - 1
    await driver.send_command("C5", command="SDT0,50,200")
    await pip_be.liha.discard_disposable_tip_high(tips_mask)
    await sync_tip_state()
    return f"Tips ejected (mask={tips_mask:#x})"
  elif action == "ree":
    resp = await driver.send_command("C5", command="REE0")
    err = resp["data"][0] if resp and resp.get("data") else ""
    resp2 = await driver.send_command("C5", command="REE1")
    cfg = resp2["data"][0] if resp2 and resp2.get("data") else ""
    names = {0: "OK", 1: "Init failed", 7: "Not init", 25: "Tip not fetched"}
    lines = []
    for i, (ax, ec) in enumerate(zip(cfg, err)):
      code = ord(ec) - 0x40
      label = f"{ax}{i - 2}" if ax == "Z" else ax
      lines.append(f"{label}={names.get(code, f'err{code}')}")
    return " | ".join(lines)
  elif action == "lamp_green":
    await driver.send_command("O1", command="SSL1,1")
    return "Lamp: SSL1,1 (green on)"
  elif action == "lamp_off":
    await driver.send_command("O1", command="SSL1,0")
    return "Lamp: SSL1,0 (off)"
  elif action == "lamp_test":
    # Try various commands to find what controls the lamp
    results = []
    for cmd in ["SSL1,1", "SSL2,1", "SPS1", "SPS2", "SPS3"]:
      try:
        await driver.send_command("O1", command=cmd)
        results.append(f"O1,{cmd}: OK")
      except Exception as e:
        results.append(f"O1,{cmd}: {e}")
      import asyncio
      await asyncio.sleep(1)
    # Reset
    await driver.send_command("O1", command="SSL1,0")
    await driver.send_command("O1", command="SPS0")
    return " | ".join(results)
  elif action == "power_on":
    await driver.send_command("O1", command="SPN")
    await driver.send_command("O1", command="SPS3")
    return "Motor power: SPN + SPS3"
  elif action == "power_off":
    await driver.send_command("O1", command="SPS0")
    return "Motor power: SPS0 (off)"
  elif action == "gripper_open":
    await driver.send_command("C1", command="PAG900")
    return "Gripper opened (G=900)"
  return f"Unknown action: {action}"


def load_json_file(path):
  if os.path.exists(path):
    with open(path, "r") as f:
      return json.load(f)
  return {}


def save_json_file(path, data):
  with open(path, "w") as f:
    json.dump(data, f, indent=2)


connected = False


def build_deck():
  """Build the deck and EVO device WITHOUT connecting to hardware."""
  global evo, tip_racks

  from labware_library import (
    DeepWell_96_Round_Corrected,
    DiTi_50ul_SBS_LiHa_Air,
    DiTi_200ul_SBS_LiHa_Air,
    DiTi_1000ul_SBS_LiHa_Air,
    Eppendorf_96_wellplate_250ul_Vb_skirted,
    MP_3Pos_Corrected,
  )
  from pylabrobot.resources.tecan.tecan_decks import EVO150Deck
  from pylabrobot.tecan.evo import TecanEVO

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

  # Rail 4: 50uL tips + Eppendorf plates
  carrier_r4 = MP_3Pos_Corrected("carrier_r4")
  deck.assign_child_resource(carrier_r4, rails=4)
  carrier_r4[0] = Eppendorf_96_wellplate_250ul_Vb_skirted("source_r4")
  carrier_r4[1] = Eppendorf_96_wellplate_250ul_Vb_skirted("dest_r4")
  tips_50 = DiTi_50ul_SBS_LiHa_Air("tips_50ul")
  carrier_r4[2] = tips_50

  # Rail 16: 200uL tips + Eppendorf plates
  carrier_r16 = MP_3Pos_Corrected("carrier_r16")
  deck.assign_child_resource(carrier_r16, rails=16)
  carrier_r16[0] = Eppendorf_96_wellplate_250ul_Vb_skirted("source_r16")
  carrier_r16[1] = Eppendorf_96_wellplate_250ul_Vb_skirted("dest_r16")
  tips_200 = DiTi_200ul_SBS_LiHa_Air("tips_200ul")
  carrier_r16[2] = tips_200

  # Rail 26: 1000uL tips + deep-well plates
  carrier_r26 = MP_3Pos_Corrected("carrier_r26")
  deck.assign_child_resource(carrier_r26, rails=26)
  carrier_r26[0] = DeepWell_96_Round_Corrected("source_r26")
  carrier_r26[1] = DeepWell_96_Round_Corrected("dest_r26")
  tips_1000 = DiTi_1000ul_SBS_LiHa_Air("tips_1000ul")
  carrier_r26[2] = tips_1000

  tip_racks = {
    "50": tips_50,
    "200": tips_200,
    "1000": tips_1000,
  }

  print("Deck built (not connected).")


async def connect_evo():
  """Connect to the EVO hardware."""
  global driver, connected
  print("Connecting to EVO...")
  await evo.setup()
  driver = evo.driver
  connected = True
  print("EVO connected!")


async def disconnect_evo():
  """Disconnect from the EVO hardware."""
  global driver, connected
  print("Disconnecting...")
  await evo.stop()
  driver = None
  connected = False
  print("Disconnected.")


@app.route("/connect", methods=["POST"])
def connect():
  global connected
  if connected:
    return jsonify({"message": "Already connected", "connected": True})
  try:
    future = asyncio.run_coroutine_threadsafe(connect_evo(), loop)
    future.result(timeout=180)
    return jsonify({"message": "Connected!", "connected": True})
  except Exception as e:
    return jsonify({"error": str(e), "connected": False})


@app.route("/disconnect", methods=["POST"])
def disconnect():
  global connected
  if not connected:
    return jsonify({"message": "Not connected", "connected": False})
  try:
    future = asyncio.run_coroutine_threadsafe(disconnect_evo(), loop)
    future.result(timeout=30)
    return jsonify({"message": "Disconnected", "connected": False})
  except Exception as e:
    return jsonify({"error": str(e), "connected": connected})


@app.route("/connection_status")
def connection_status():
  return jsonify({"connected": connected})


def run_event_loop(lp):
  """Run the asyncio event loop in a background thread."""
  asyncio.set_event_loop(lp)
  lp.run_forever()


if __name__ == "__main__":
  # Install flask
  try:
    import flask  # noqa: F401
  except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "-q"])

  # Create event loop in background thread
  loop = asyncio.new_event_loop()
  thread = threading.Thread(target=run_event_loop, args=(loop,), daemon=True)
  thread.start()

  # Build deck (no hardware connection)
  build_deck()

  print("\n" + "=" * 50)
  print("  Open http://localhost:5050 in your browser")
  print("  Click 'Connect' to connect to the EVO")
  print("=" * 50 + "\n")

  app.run(host="0.0.0.0", port=5050, debug=False)
