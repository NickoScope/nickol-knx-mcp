# Room Template format — public contract (schema_version 1)

A room template is a **locale-neutral** YAML file describing the *functions* of a
room. `compose_rooms` turns a list of rooms into a new KNX project (group-address
structure + ETS import files + a device BOM proposal).

> Stability: the schema is a public contract — a breaking change forces user
> migrations. Every template MUST carry `schema_version`. Identity of a template
> and of every slot is a semantic **ID**, never a human name; renaming a label
> never changes identity or the generated addresses.

## Top-level keys

| key | required | meaning |
|-----|----------|---------|
| `schema_version` | yes | `1`. Guards compatibility/migration. |
| `slot_id` | yes | Locale-neutral ASCII identifier (`[a-z0-9_]+`). The template's identity. |
| `labels` | yes | `{ru: …, en: …}` — presentation only (RU/EN). |
| `parameters` | yes | Named parameters with a `default` (and provenance). |
| `slots` | yes | List of functional slots (see below). |
| `automation_intents` | no | **Non-executable** metadata declarations only. |

## Parameters

Each parameter has a `default`. `area_m2` is special: it is a **hint** that seeds
defaults, not a normative fact — it MUST be declared `role: hint` and carry
`provenance`. In R1 area does not change GA counts; it documents the sizing
assumption only.

```yaml
parameters:
  lighting_circuits:
    default: 2
    provenance: {source: preset_rule, note: "why this default"}
  area_m2:
    default: 28
    role: hint
    provenance: {source: preset_default, user_overridden: false, note: "recommender only"}
```

## Slots and per-slot presets

A slot is a functional block. Each slot declares **both** a `basic` and a
`comfort` preset — presets are *per-slot*, not one monolithic room level, so a
house can pick e.g. comfort climate with basic lighting. A preset is either
`{enabled: false}` or `{enabled: true, function: <type>, multiplicity: {...}}`.

```yaml
slots:
  - slot_id: main_light
    labels: {ru: основной свет, en: main light}
    presets:
      basic:   {enabled: true, function: lighting_switch, multiplicity: {param: lighting_circuits}}
      comfort: {enabled: true, function: lighting_dimmer, multiplicity: {param: lighting_circuits}}
```

`multiplicity` is `{fixed: N}` or `{param: <declared parameter>}` — how many
instances (circuits, windows, zones) the slot expands to.

### Function types (function-first)

Each function type expands into a fixed set of KNX communication objects, each
with a canonical DPT and a command/status role:

| function | objects (role · DPT) |
|----------|----------------------|
| `lighting_switch` | on/off `1.001` · status `1.011` |
| `lighting_dimmer` | on/off `1.001` · dimming `3.007` · brightness `5.001` · status `1.011` · brightness-status `5.001` |
| `shutter` | up/down `1.008` · stop `1.010` · position `5.001` · position-status `5.001` |
| `climate_floor` | on/off `1.001` · setpoint `9.001` · mode `20.102` · +3 statuses · actual-temp `9.001` |
| `presence` | occupancy `1.018` · illuminance `9.004` |

Every controllable command gets its status object — the generated project passes
`check_missing_status`, `check_dpt`, `check_naming` and `check_policy` cleanly.

## Address allocation (default taxonomy)

`main` = function domain, `middle` = role/sub-function, `sub` = sequential:

```
0 Central · 1 Lighting · 2 Shutters · 3 HVAC · 4 Sensors · 5 Energy · 6 Diag · 7 Reserve
```

Allocation is deterministic and **permutation-invariant** (rooms are sorted by a
canonical key before allocation), so the same *set* of rooms always yields the
same addresses regardless of input order. Sub-address exhaustion (> 255 in a
middle group) raises a hard error — never a silent overflow.

## automation_intents (declarations only)

Logic (presence→light, wind→shutter) is **not** executed by the templates. It is
declared as metadata for the upper layer (Home Assistant / the KNX program):

```yaml
automation_intents:
  - intent: presence_lights_off
    description: "Turn lights off when unoccupied."
    criticality: convenience        # or safety_related
    implementation: external
```

## Not in R1

Docking into an existing project (allocation lockfile, drift detection), exact
device selection with channel/price optimisation, and premium presets are R2 —
see `docs/roadmap/room-library/implementation-plan.md`.
