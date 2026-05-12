# Tecan EVO Hardware Testing Checklist

## Pre-Test Setup

### Equipment Required
- [x] EVO 150 powered on
- [x] USB cable connected to pylabrobot PC
- [x] EVOware PC disconnected from USB (only one client at a time)
- [x] DiTi 50uL SBS tips loaded (position 3 on MP_3Pos at rail 16)
- [x] Eppendorf 96-well plate with water in column 1 (position 1)
- [x] Empty Eppendorf 96-well plate (position 2)
- [x] `.venv` activated, `pip install -e ".[usb]"` done

### Software
- [x] `liquid-handling-testing` branch checked out (off `v1b1-tecan-evo`)
- [x] `keyser-testing/labware_library.py` has corrected carrier + plate definitions

---

## Test 1: Initialization (Cold Boot) PASSED

**Script:** `keyser-testing/test_v1b1_init.py`
**Date:** 2026-03-30

| Step | Expected | Pass? |
|------|----------|-------|
| USB connection | "USB connected" | [x] ~3s |
| ZaapMotion boot exit | All 8 tips XP2000/ZMA | [x] |
| ZaapMotion motor config | 33 commands x 8 tips OK | [x] |
| Safety module (SPN/SPS3) | OK | [x] |
| PIA (all axes) | REE0 = `@@@@@@@@@@@` | [x] |
| RoMa init + park | OK (~56s first time) | [x] |
| LiHa range queries | num_channels=8, z_range~2100 | [x] |
| Plunger init | PID, PVL, PPR sequence completes | [x] |

---

## Test 2: Initialization (Warm Reconnect) PASSED

**Date:** 2026-03-30

| Step | Expected | Pass? |
|------|----------|-------|
| REE0 check | Not "A" or "G" -> skip full init | [x] |
| RoMa REE check | `@@@@@` -> skip RoMa PIA | [x] |
| Quick setup | Channel count + ranges loaded fast | [x] |
| Total time | **3.4 seconds** (vs ~60s for full init) | [x] |

### Notes
- Fixed RoMa warm reconnect: now checks REE before PIA (was 56s, now 0.0s)
- Fixed USB buffer drain: uses 1s packet timeout instead of 30s
- Fixed `_is_initialized`: REE0 response cast to str (was int for some states)

---

## Test 3: Tip Pickup PASSED

**Script:** `keyser-testing/test_v1b1_pipette.py`
**Date:** 2026-04-02

| Step | Expected | Pass? |
|------|----------|-------|
| X/Y positioning | Channels aligned over tip column | [x] |
| Z approach | Channels descend to tips | [x] AGT executes |
| Tip engagement | Force feedback engages all 8 tips | [x] |
| Z retract | Channels lift with tips mounted | [x] |
| RTS check | Tip status = 255 (all mounted) | [x] |

### Fixes Applied
- **Carrier site locations corrected**: X 5.5->11.0, Y +0.9, Z +1.2 (from EVOware measurements)
- **Plate dx corrected**: 6.76->11.64 (SBS/SLAS P1=14.38mm standard)
- **Per-labware x_offset/y_offset removed** — no longer needed
- Residuals within 0.7mm (manual teaching precision)

---

## Test 4: Tip Drop PASSED

**Date:** 2026-04-02

| Step | Expected | Pass? |
|------|----------|-------|
| Move to tip box column 1 | Channels aligned over tips | [x] |
| Plunger empty | PPA0 completes | [x] |
| SDT + ADT | Tips released | [x] |
| RTS check | Tip status = 0 (none mounted) | [x] |
| Z retract | Channels raised to Z max | [x] |

---

## Test 5: Aspirate — PASSED

**Date:** 2026-04-07

### Fixes Applied
- `set_search_z_start` (STL) was sending syringe-transformed Z coordinates (~2381)
  instead of absolute Tecan Z. Fixed to use `z_asp` / `z_asp_max` computed with
  plate z_start/z_max + tip_extension. Error was "Invalid operand" (code 3).
- Replaced hardcoded nesting depth (50) with `tip.fitting_depth` for accuracy.
- 50uL tip: total_tip_length=58.0mm, fitting_depth=4.9mm, tip_ext=531 units (53.1mm).

| Step | Expected | Pass? |
|------|----------|-------|
| Move to source plate | Channels over column 1 | [x] |
| Leading airgap | Force mode + plunger move | [x] |
| LLD (if enabled) | Liquid detected | [x] |
| Aspirate 25uL | Tracking move completes | [x] |
| Trailing airgap | Force mode + plunger move | [x] |
| Z retract | Channels lift to z_start | [x] |

---

## Test 6: Dispense — PASSED

**Date:** 2026-04-07

### Fixes Applied
- Updated z_dispense from 200 to 99 (taught well bottom) for small volume dispensing.
- Dispense Z target = z_dispense(99) + tip_ext(531) = 630 — tips at well bottom.

| Step | Expected | Pass? |
|------|----------|-------|
| Move to dest plate | Channels over column 1 | [x] |
| Dispense 25uL | Tracking move completes | [x] |
| Z retract | Channels lift | [x] |

---

## Test 7: Full Cycle — PASSED

**Date:** 2026-05-05

| Step | Pass? | Notes |
|------|-------|-------|
| Init | [x] | Cold + warm both work |
| Tip pickup | [x] | Working with corrected coordinates |
| Aspirate | [x] | STL fix + fitting_depth validated |
| Dispense | [x] | z_dispense=99 (well bottom) |
| Tip drop | [x] | Working |
| Clean stop | [x] | |

---

## Test 8b: Volume Accuracy Diagnostic — PASSED

**Script:** `keyser-testing/test_v1b1_volume_diagnostic.py`
**Date:** 2026-05-05

Tests 100uL transfers with 200uL tips, isolating variables that affect volume accuracy.

| Test | Column | Result |
|------|--------|--------|
| Baseline (plain aspirate + dispense) | 4 | Accurate |
| Blow-out (15uL air after dispense) | 5 | Accurate |
| Pre-wet (3x mix before aspirate) | 6 | Accurate |
| Pre-wet + Blow-out | 7 | Accurate |

### Fixes Applied
- **Air backend blow-out bug**: `air_pip_backend.py` `dispense()` was not calling
  `_perform_blow_out()` — blow_out_air_volume was silently ignored. Fixed.
- **Blow-out plunger overrun**: `_dispense_action()` was pushing out all air
  (lag + tag + liquid), leaving zero plunger travel for blow-out. Fixed by holding
  back air gap volume from main dispense when blow-out is requested.
- **Blow-out volume capped**: `_perform_blow_out()` now caps at available air
  (lag + tag from liquid class) to prevent plunger overrun errors.

### Initial Misdiagnosis
First run showed 60-70uL shortfall on all tests — root cause was **50uL tips loaded
instead of 200uL tips**. 50uL tips max out at 55uL, so 100uL commands physically
couldn't be fulfilled. With correct 200uL tips, all tests passed including baseline.

---

## Test 8: RoMa Plate Handling — PASSED

**Date:** 2026-04-08

### Fixes Applied
- Calibrated `roma_x` (1878 → 1670) and `roma_y` (423 → 380) from taught positions
- Created `TecanGripperArm(GripperArm)` to route `move_resource` through carrier-based backend
- High-level API now works: `evo.arm.move_resource(plate, carrier_dst[0])`

| Step | Expected | Pass? |
|------|----------|-------|
| Pick up from carrier_src[0] | Plate gripped | [x] |
| Place at carrier_dst[0] | Plate released in position | [x] |
| Move carrier_dst[0] → [1] → [2] | All 3 positions work | [x] |
| Return to carrier_src[0] | Plate back at origin | [x] |
| Resource tracking | plate.parent updates automatically | [x] |

---

## Z-Calibration Procedure

Use `keyser-testing/jog_ui.py` (web UI at http://localhost:5050):

1. **Tip rack z_start**: Jog to just above tip tops, teach `z_start` for `tips`
2. **Tip rack z_max**: Jog to bottom of tip search range, teach `z_max` for `tips`
3. **Plate z_start**: Jog bare channel to plate top surface, teach `z_start` for plate
4. **Plate z_dispense**: Jog to dispense height, teach `z_dispense` for plate
5. **Plate z_max**: Jog to maximum depth, teach `z_max` for plate

**With tips mounted**: Select the tip type in the "Mounted" dropdown before teaching.
The UI automatically subtracts tip extension to store bare-channel Z values.

Taught positions saved in `keyser-testing/taught_positions.json`.
Labware edits saved in `keyser-testing/labware_edits.json`.

### Important Z Notes
- Tecan Z coordinate system: 0 = deck surface, z_range (~2100) = top/home
- Taught positions are measured with **bare channels** (no tip mounted) unless
  the tip type dropdown is set in the jog UI
- For aspirate/dispense with tips: Z target = plate.z_start + tip_extension
  - tip_extension = total_tip_length * 10 - nesting_depth (50 units / 5mm)
- AGT z_start/z_max are used directly (no tip extension needed — tips not yet mounted)

---

## Tools Available

| Tool | Purpose |
|------|---------|
| `keyser-testing/jog_ui.py` | Web UI for jogging, teaching, labware inspection |
| `keyser-testing/jog_and_teach.py` | CLI jog/teach tool |
| `keyser-testing/load_tips.py` | Pick up tips from selected column (1-12) |
| `keyser-testing/tips_off.py` | Emergency tip removal (raw firmware commands) |
| `keyser-testing/tips_off_tipbox.py` | Drop tips back into tip box at selected column |
| `keyser-testing/eject_tips_home.py` | Eject tips at home position |
| `keyser-testing/transfer_tips.py` | Transfer tips from one rack column to another |
| `keyser-testing/test_v1b1_init.py` | Init test with timing |
| `keyser-testing/test_v1b1_pipette.py` | Full pipetting cycle test (50uL tips) |
| `keyser-testing/test_v1b1_pipette_200ul.py` | Pipetting test — 200uL tips, 100uL volume |
| `keyser-testing/test_v1b1_pipette_1000ul.py` | Pipetting test — 1000uL tips |
| `keyser-testing/test_v1b1_pipette_200ul_multi_col.py` | Multi-column transfer — cols 4, 5, 6 |
| `keyser-testing/test_v1b1_roma.py` | RoMa plate handling test |
| `keyser-testing/test_v1b1_volume_diagnostic.py` | Volume accuracy diagnostic (baseline, blow-out, pre-wet) |
| `keyser-testing/labware_library.py` | Custom labware definitions (carriers, plates, tips) |

---

## Coordinate Fix Summary (2026-04-02)

Root cause of systematic X/Y offset identified and fixed:

1. **Plate well dx was wrong**: 6.76mm placed A1 center at 9.50mm from plate edge.
   SBS/SLAS 4-2004 standard P1=14.38mm. Fixed dx to 11.64mm.

2. **Carrier site X offset was wrong**: Upstream MP_3Pos had site X=5.5mm.
   EVOware carrier editor shows 11.0mm. Fixed in `MP_3Pos_Corrected`.

3. **Per-labware x_offset/y_offset hacks removed** — no longer needed.

| Parameter | Upstream | Corrected |
|-----------|----------|-----------|
| Plate dx | 6.76 | 11.64 |
| Site X | 5.5 | 11.0 |
| Site Y | 13.5 / 109.5 / 205.5 | 14.4 / 109.4 / 205.4 |
| Site Z | 62.5 | 63.7 |
| Carrier off_x | 12.0 | 12.0 (unchanged) |
| Carrier off_y | 24.7 | 24.7 (unchanged) |

---

## Test 9: Multi-Tip-Size Cycle — NOT STARTED

Run the same pipetting workflow (pick up, aspirate, dispense, drop) with all three
tip sizes to validate end-to-end accuracy across the full tip range.

| Tip Size | Volume | Pick up | Aspirate | Dispense | Drop | Pass? |
|----------|--------|---------|----------|----------|------|-------|
| 50uL | 25uL | [ ] | [ ] | [ ] | [ ] | |
| 200uL | 100uL | [ ] | [ ] | [ ] | [ ] | |
| 1000uL | 500uL | [ ] | [ ] | [ ] | [ ] | |

---

## Test 10: Serial Dilution — NOT STARTED

Aspirate from source, dispense into dest column, then re-aspirate from that dest column
and dispense into the next — tests multi-step liquid handling accuracy and carryover.

| Step | Source | Dest | Volume | Pass? |
|------|--------|------|--------|-------|
| Transfer 1 | source col 1 | dest col 1 | 100uL | [ ] |
| Transfer 2 | dest col 1 | dest col 2 | 100uL | [ ] |
| Transfer 3 | dest col 2 | dest col 3 | 100uL | [ ] |

---

## Test 11: 384-Well Plate Positioning — NOT STARTED

Validate positioning accuracy with 384-well plates (3.6mm well diameter, 4.5mm pitch).
Critical for verifying per-channel X alignment (see Known Issue #6).

**Prerequisites:** 384-well plate definition in labware_library.py, plate Z-positions taught.

| Step | Expected | Pass? |
|------|----------|-------|
| Tip pickup (200uL) | Tips mounted | [ ] |
| Move to 384-well col 1 | All 16 rows accessible (2x8) | [ ] |
| Aspirate from col 1 | No tip-wall contact / crash | [ ] |
| Dispense into col 2 | Centered in wells | [ ] |
| Visual alignment check | Tips centered at depth | [ ] |

---

## Test 12: Liquid Level Detection (LLD) Validation — NOT STARTED

Test LLD at different fill levels to verify detection accuracy and reliability.

| Fill Level | Expected Z | Detected Z | Delta | Pass? |
|------------|-----------|------------|-------|-------|
| Full (~200uL/well) | | | | [ ] |
| Half (~100uL/well) | | | | [ ] |
| Low (~25uL/well) | | | | [ ] |
| Empty (air) | Should fail/timeout | | | [ ] |

---

## Known Issues / TODO

1. ~~Aspirate STL fix~~ — validated 2026-04-07
2. ~~Dispense~~ — validated 2026-04-07 with z_dispense=99
3. ~~Init ordering changed~~ — PIP before RoMa validated on cold boot 2026-04-08
4. ~~200uL / 1000uL tips~~ — fitting_depth=11.0mm measured on hardware, all 3 sizes validated (50uL/200uL/1000uL) 2026-04-09
5. ~~RoMa plate handling~~ — validated 2026-04-08, move_resource API working
6. **Per-channel X alignment drift at depth** — channels appear aligned at home Z but show small X offsets as they descend, likely due to slightly non-vertical Z shafts. Causes tips to contact well walls instead of centering. Functional for 96-well plates (6.8mm opening) but may be a risk for 384-well (3.6mm opening). No software fix — firmware only supports a single X position for all channels. Mechanical correction (shaft straightening) required if 384-well work is needed. Observed 2026-05-06.
