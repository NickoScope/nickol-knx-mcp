# From spec (ТЗ) to group-address structure

`nickol-knx-mcp` reads and validates a finished `.knxproj`. But the harder, higher-value
direction is the reverse: **from a project spec, design the group-address structure** a
professional would build. This note describes the method and the tools that support it.

## Why one device ≠ one group address
A spec says "4-channel dimmer, 8 shutters, AC in every room". Each of those expands into a
*set* of communication objects, each with its own DPT:

- a **dimmer channel** → on/off · on/off-status · relative-dim (3.007) · absolute value
  (5.001) · brightness-status (5.001)
- a **shutter channel** → up/down (1.008) · stop (1.010) · position (5.001) · position-status
- an **AC unit** → on/off · mode (20.105) · setpoint (9.001) · fan · ambient-temp · statuses

The `decompose_device` tool encodes these recipes:

```
decompose_device("ZDIDBDX4", channels=4)   → 5 objects/channel × 4 = 20 GA (with DPTs)
decompose_device("JRA/S")                    → ABB shutter recipe (1.008/1.010/5.001)
decompose_device("Z50")                      → panel: 0 new GAs (references existing)
```

`list_device_recipes` lists the built-in library (Zennio + ABB families; more via the same
schema).

## The pipeline
```
spec / ТЗ
  → device list + quantities                 (what equipment, per room)
  → decompose_device per type                (device → object recipe + DPT)
  → command/status discipline                (every actuator gets its status GA)
  → logic layer                              (central macros, zone groups, scenes,
                                              motion/HVAC/shutter automation, reserves)
  → validated group-address structure        (analyze_all → 0 errors)
  → generate_ets_group_addresses (XML)       (import into ETS)
```

## What is reproducible from a spec — and what is not (measured, honestly)
Validated by designing a full structure from a real project's spec and comparing to the
as-built export:

- **Reproducible ≈ 90%+**: the *taxonomy* (function-domain main groups), *domains*, the
  *logic structure*, *command/status pairing*, and *DPT discipline*.
- **NOT derivable from a spec**: the exact *object count* per device. Integrators enable a
  subset of each device's master object menu, and how large that subset is varies **2–9×
  between projects** — it is a design choice living in the ETS parameter config, not in the
  spec. So the device library gives the object *menu*; the exact count needs the real
  project. Predict a **range**, never a false-precise number.

Bottom line: a spec plus this method reproduces the *structure* of a professional design to
~90%; the last mile is the integrator's per-device parameterisation.

## Safety
Everything here is design-time and read-only. The server has no KNX/IP bus libraries — it
cannot reach an installation. Always produce a report and review it before importing into
ETS or deploying to Home Assistant.
