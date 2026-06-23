# Tecan EVO Testing Kanban

## Legend

- **Lane**: Tests in the same lane can run in parallel (no hardware conflicts)
- **Deps**: Must complete before this test starts
- **HW**: Hardware resources required (LiHa = liquid handling arm, RoMa = robotic arm)

---

## DONE

| Test | Description |
|------|-------------|
| T1 | Init (Cold Boot) |
| T2 | Init (Warm Reconnect) |
| T3 | Tip Pickup |
| T4 | Tip Drop |
| T5 | Aspirate |
| T6 | Dispense |
| T7 | Full Cycle |
| T8 | RoMa Plate Handling |
| T8b | Volume Accuracy Diagnostic |

---

## NOT STARTED — Execution Plan

### Phase 1: Independent Tests (can run in parallel across sessions)

These have no dependencies on each other, only on the completed tests above.

```
┌─────────────────────────────────┐  ┌─────────────────────────────────┐
│  LANE A: LiHa-Only              │  │  LANE B: RoMa-Only              │
│  (needs tips + plates)           │  │  (needs plates + carriers)      │
│                                  │  │                                  │
│  T9:  Multi-Tip-Size Cycle       │  │  T19: RoMa Speed Tuning         │
│       50uL/200uL/1000uL         │  │       Test non-default speeds    │
│       Deps: T7 ✓                 │  │       Deps: T8 ✓                │
│                                  │  │                                  │
│  T12: LLD Validation             │  │                                  │
│       Full/half/low/empty        │  │                                  │
│       Deps: T5 ✓                 │  │                                  │
│                                  │  │                                  │
│  T13: Tip Touch Validation       │  │                                  │
│       Y-offset wall contact      │  │                                  │
│       Deps: T6 ✓                 │  │                                  │
│                                  │  │                                  │
│  T15: Partial Channel Pickup     │  │                                  │
│       1, 4, <8 channels          │  │                                  │
│       Deps: T3 ✓                 │  │                                  │
└─────────────────────────────────┘  └─────────────────────────────────┘
```

**Parallelization note:** Lane A tests are *sequentially exclusive* with each other
(they all need LiHa), but the entire Lane A batch is independent from Lane B.
Within Lane A, T9/T12/T13/T15 can run in any order but not simultaneously.

### Phase 2: Depends on Phase 1 results

```
┌─────────────────────────────────┐  ┌─────────────────────────────────┐
│  LANE A: LiHa Volume Tests      │  │  LANE B: LiHa Liquid Types      │
│                                  │  │                                  │
│  T10: Serial Dilution            │  │  T17: Viscous/Volatile Liquids   │
│       Multi-step transfers       │  │       DMSO, EtOH, glycerol      │
│       Deps: T9                   │  │       Deps: T9, T13             │
│                                  │  │                                  │
│  T16: Volume Linearity           │  │  T14: Mixing Cycle              │
│       10%/50%/90% per tip size   │  │       Resuspension validation   │
│       Deps: T9                   │  │       Deps: T5 ✓               │
│                                  │  │                                  │
│  T11: 384-Well Positioning       │  │  T18: Fast Z (PAZ) Validation   │
│       Deps: T9, Issue #8 eval   │  │       Deps: T5 ✓               │
│       ⚠ blocked by mech issue   │  │                                  │
└─────────────────────────────────┘  └─────────────────────────────────┘
```

**Parallelization note:** Lane A and B are mutually exclusive (both need LiHa).
Within each lane, tests are sequential. But you choose which lane to run first.

### Phase 3: Integration & Stress (depends on Phase 1 + 2)

```
┌─────────────────────────────────────────────────────────────────────┐
│  LANE: Full System (LiHa + RoMa together)                          │
│                                                                      │
│  T20: Combined RoMa + LiHa Workflow                                 │
│       Move plate, then pipette into it                               │
│       Deps: T8 ✓, T9, T19                                          │
│                                                                      │
│  T24: Collision Detection                                            │
│       Verify arm position caching prevents crashes                   │
│       Deps: T20                                                      │
│                                                                      │
│  T23: Endurance / Reliability                                        │
│       50+ full cycles continuous                                     │
│       Deps: T7 ✓, T9                                                │
└─────────────────────────────────────────────────────────────────────┘
```

### Phase 4: Robustness (run anytime, independent)

```
┌─────────────────────────────────────────────────────────────────────┐
│  LANE: Error & Recovery (can run independently)                      │
│                                                                      │
│  T21: Error Recovery                                                 │
│       Force errors, verify clean recovery                            │
│       Deps: T1 ✓, T2 ✓                                             │
│                                                                      │
│  T22: USB Disconnect Recovery                                        │
│       Pull USB mid-op, reconnect, verify warm reconnect              │
│       Deps: T2 ✓                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Suggested Execution Order (Fastest Path)

Assuming one EVO, one operator:

```
Day 1:  T15 (partial channels) → T9 (multi-tip) → T12 (LLD)
Day 2:  T13 (tip touch) → T14 (mixing) → T18 (fast Z)
Day 3:  T19 (RoMa speed) → T10 (serial dilution) → T16 (volume linearity)
Day 4:  T20 (combined workflow) → T24 (collision detection)
Day 5:  T21 (error recovery) → T22 (USB recovery) → T23 (endurance)
```

T11 (384-well) deferred until mechanical Issue #8 is resolved.
T17 (viscous/volatile) deferred until liquid classes are defined.

---

## Automated Methods (Post-Validation)

### A. Startup Hardware Test Routine

Run at each power-on or new deck layout to verify the system is operational.

| Check | Method | Pass Criteria |
|-------|--------|---------------|
| Init health | Cold/warm boot | All axes REE0 = initialized |
| Tip pickup/drop | Pick 8, drop 8 | RTS = 255 then 0 |
| LLD check | Detect known water level | Z within ±5 units of taught |
| RoMa pick/place | Move plate to known position | Gripper position delta < 2mm |
| Volume spot-check | Aspirate 100uL, gravimetric check | Within ±5% |

### B. Automated Liquid Class Development

Systematic characterization of new liquid types:

| Step | Method |
|------|--------|
| 1. Gravimetric baseline | Weigh plate, aspirate/dispense N volumes, reweigh |
| 2. Parameter sweep | Vary aspirate speed, dispense speed, blow-out vol, pre-wet cycles |
| 3. CV optimization | Run 8-replicates at each parameter combo, minimize CV |
| 4. Edge volume testing | Test at 10%, 50%, 90% tip capacity |
| 5. Export liquid class | Save optimal parameters as reusable liquid class definition |

### C. Monthly QA Routine

| Check | Method | Acceptance |
|-------|--------|------------|
| Volume accuracy | 8-channel gravimetric, 3 volumes per tip size | CV < 3%, bias < 5% |
| Positioning | Dye dispense into clear plate, image | All wells centered |
| LLD consistency | 10 replicates at 3 fill levels | Z CV < 2 units |
| RoMa repeatability | 10 pick/place cycles, measure final position | < 1mm drift |
| Endurance | 20 full cycles without error | Zero errors |
