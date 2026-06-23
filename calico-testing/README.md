# Keyser Testing — PyLabRobot Hardware Testing & Protocol Runner

Local testing scripts, calibration data, and the Protocol Runner application for the Tecan EVO 150 with Air LiHa (ZaapMotion), RoMa, and supporting instruments.

## Setup

### 1. Python Environment

```bash
cd pylabrobot
python -m venv .venv
.venv/Scripts/activate   # Windows
# source .venv/bin/activate  # Linux/Mac

pip install -e ".[usb,serial]"
```

### 2. Protocol Runner Dependencies

```bash
pip install fastapi uvicorn python-dotenv google-genai websockets
```

### 3. AI Assistant (optional)

Get an API key from https://aistudio.google.com/apikey

Create a `.env` file in the repo root:

```
GEMINI_API_KEY=your-api-key-here
```

## Running the Protocol Runner

```bash
python -m pylabrobot.runner --lib keyser-testing
```

Opens at http://localhost:5051 with:
- Deck visualization (left panel)
- Code editor with protocol save/load (center panel)
- AI assistant for natural language protocol generation (right panel)
- Real-time channel state and arm position panels
- Console output

### API Documentation

- Swagger UI: http://localhost:5051/docs
- ReDoc: http://localhost:5051/redoc

## Hardware Testing Scripts

All scripts assume the EVO is connected via USB and use the corrected labware definitions in `labware_library.py`.

### Initialization

```bash
python keyser-testing/test_v1b1_init.py          # Cold/warm boot test
```

### Pipetting (50/200/1000 uL tips)

```bash
python keyser-testing/test_v1b1_pipette.py           # 50uL tips, 25uL transfer
python keyser-testing/test_v1b1_pipette_200ul.py      # 200uL tips, 100uL transfer
python keyser-testing/test_v1b1_pipette_1000ul.py     # 1000uL tips, 100uL transfer
```

### Tip Management

```bash
python keyser-testing/load_tips.py [50|200|1000] [column]     # Pick up tips
python keyser-testing/tips_off_tipbox.py [50|200|1000] [column]  # Drop tips back
python keyser-testing/eject_tips_home.py                       # Emergency eject at home
```

### RoMa Plate Handling

```bash
python keyser-testing/test_v1b1_roma.py    # Multi-position plate move test
```

### Jog & Teach UI

```bash
python keyser-testing/jog_ui.py    # Web UI at http://localhost:5050
```

Keyboard controls:
- **LiHa**: Numpad 4/6 (X), 8/2 (Y), +/- (Z), 7/9 (step size)
- **RoMa**: Arrow keys (X/Y), PgUp/PgDn (Z), Home/End (R), [/] (gripper)

## Deck Layout

Default configuration (rail 16):

| Position | Resource |
|----------|----------|
| 1 | Source plate (Eppendorf 96-well V-bottom) |
| 2 | Destination plate |
| 3 | Tip rack (swappable: 50/200/1000 uL) |

Second carrier on rail 22 for RoMa plate handling tests.

## Tip Dimensions (measured on hardware)

| Tip | Length | Fitting Depth | Extension |
|-----|--------|--------------|-----------|
| 50 uL | 58.0 mm | 11.0 mm | 47.0 mm |
| 200 uL | 58.5 mm | 11.0 mm | 47.5 mm |
| 1000 uL | 96.1 mm | 11.0 mm | 85.1 mm |

## Key Files

| File | Purpose |
|------|---------|
| `labware_library.py` | Corrected carrier, plate, and tip definitions |
| `labware_edits.json` | Taught Z positions from jog UI |
| `taught_positions.json` | Saved LiHa/RoMa positions |
| `hardware_testing_checklist.md` | Test status tracking |
