# Tecan EVO Jog & Teach UI

Web-based control panel for jogging and teaching positions on a Tecan EVO liquid handler. Built on Flask + PyLabRobot.

## Quick Start

```bash
python keyser-testing/jog_ui.py
# Open http://localhost:5050 in your browser
# Click "Connect" to connect to the EVO
```

Requires: `flask`, `pylabrobot`, and USB access to the EVO.

## Layout

The UI has three columns:

| Left | Center | Right |
|------|--------|-------|
| Live log | Arm positions, direct move, deck map | Labware inspector, teach controls, actions |

## Jogging the Arms

### LiHa (Numpad)

| Key | Action |
|-----|--------|
| `4` / `6` | X left / right |
| `8` / `2` | Y back (away from operator) / forward |
| `+` / `-` | Z down (toward deck) / up |
| `7` / `9` | Decrease / increase step size |

### RoMa (Arrow Keys)

| Key | Action |
|-----|--------|
| Left / Right | X left / right |
| Up / Down | Y forward / back |
| PgUp / PgDn | Z up / down |
| Home / End | R rotate |
| `[` / `]` | Gripper close / open |

Step sizes: 0.1, 0.5, 1, 2, 5, 10, 20, 50 mm.

### Direct Move

Enter X, Y, and/or Z coordinates (in mm, Tecan firmware units) in the MOVE TO box and click Go. Leave fields empty to skip that axis.

Safety: if X or Y changes, Z automatically raises to travel height first, then moves X/Y, then lowers Z.

When tips are mounted, the Z field becomes "Z tip" and the entered value targets the **tip end** position (the channel is offset by the tip extension length).

### Deck Map

Click anywhere on the deck map to move the LiHa to that X/Y position (Z raises first). The map shows labware as colored rectangles and live arm positions as crosshairs (red = LiHa, teal = RoMa).

## Teaching Labware Positions

Teaching calibrates where the LiHa should go for each piece of labware. Each labware has Z parameters:

- **z_start**: just above the plate/tip top (search start)
- **z_dispense**: dispense height inside the well
- **z_max**: maximum safe depth (near well bottom)

### Workflow

1. **Pick up tips** if teaching plate positions (tip racks are taught bare)
2. The "Mounted" dropdown auto-updates when you pick up/drop tips
3. In the **Teach Checklist**, click **Go** next to a position to move there
   - The arm moves to the labware's A1 well at the current Z value
   - The teach point auto-selects so you can immediately re-teach
4. **Jog** with numpad keys to fine-tune the position
5. Click **Set** next to the position to save the current Z as the new value
   - Tip extension is automatically subtracted (stored as bare-channel Z)
6. Click **Undo** to revert the last teach if needed

### Teach Checklist Icons

| Icon | Meaning |
|------|---------|
| `~` (yellow) | Default value (not yet taught from hardware) |
| `*` (green) | Taught from hardware |
| `x` (red) | No value set |

### Go To Modes

- **Z only** (default): moves only Z, keeps current X/Y. Safe for quick checks.
- **XYZ**: raises Z, shows confirmation dialog with target coordinates, then moves X/Y/Z on Enter. Use this to travel to a labware position from anywhere on the deck.

### Tip-Aware Movement

When tips are mounted:
- The LiHa position box shows a gold **Z tip** row with the tip end position
- Go To commands offset Z by the tip extension so the tip end arrives at the taught position
- Direct Move Z targets the tip end, not the channel
- The compact readout above teach controls shows live positions

## Tip Management

- **Pick Up**: select tip type (50/200/1000 uL) and column, click Pick Up
- **Drop**: return tips to the same rack position
- **Eject Tips**: emergency eject (bypasses rack tracking)
- **Check Tips**: query firmware tip status (RTS)

The mounted tip type auto-syncs between the Tip Management and Teach sections.

## Actions

| Button | What it does |
|--------|-------------|
| Home LiHa | Move to home position (X=4.5, Y=103.1) |
| Z Up (Clear) | Raise all Z channels to max travel height |
| Park RoMa | Send RoMa to park position |
| Check Tips | Report firmware tip status |
| Eject Tips | Emergency tip discard |
| Axis Status | Report axis error codes |

## Files

| File | Purpose |
|------|---------|
| `jog_ui.py` | Flask server + embedded HTML/JS UI |
| `labware_library.py` | Labware definitions (plates, tip racks, carriers) |
| `labware_edits.json` | Taught Z positions (created on first teach) |
| `taught_positions.json` | Saved named positions (created on first record) |

## Coordinate Systems

The Tecan firmware and PyLabRobot use different coordinate systems:

| | X | Y | Z |
|---|---|---|---|
| **Tecan firmware** | `(PLR_x - 100) * 10` | `(346.5 - PLR_y) * 10` | 0 = lowest, z_range = highest |
| **PLR deck** | mm from deck origin | mm from front (Y=0 = front) | mm from deck surface |

The UI displays Tecan firmware coordinates (matching what you see from RPX/RPY/RPZ). The labware inspector shows both PLR and Tecan coordinates.

## Known Limitations

- Only the LiHa arm supports Go To and Direct Move (RoMa is jog-only)
- Undo only tracks one level (the last teach)
- Deck map click always moves the LiHa, not the RoMa
- No collision detection beyond the safe Z-raise-first sequence
- Labware edits are stored in a flat JSON file, not merged back into labware definitions
