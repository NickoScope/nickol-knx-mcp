# ETS / KNX Assistant — project rules

This file is the design playbook for working on this KNX project with the
`nickol-knx` MCP server. Claude Code loads it automatically as project context.
Apply these rules when reading the `.knxproj`, generating Home Assistant config,
or producing ETS group-address exports.

## Hard safety rules
- **Never** propose writing to a live KNX bus. The `nickol-knx` server has no bus
  access; keep it that way. Live control happens only through the Home Assistant
  layer, and only when the user explicitly asks.
- **Always** generate a Markdown report (`project_report`) and let the user read
  it **before** any import into ETS or deploy into Home Assistant.
- All generated files go into the Git-tracked workspace. Commit before and after
  changes so every step is reversible.

## Two-layer architecture
- **KNX (ETS)** owns foundational logic and runs autonomously. The integrator
  programs it. Treat the `.knxproj` as the source of truth for addresses + DPTs.
- **Home Assistant** is the upper smart layer (automations, templates). HA must
  read *real device state*, never assume it.

## Group address structure (3-level Main/Middle/Sub)
- Main group = function domain. Suggested split:
  `0 Central/Scenes · 1 Lighting · 2 Shutters/Blinds · 3 HVAC · 4 Sensors ·
   5 Energy · 6 Diagnostics · 7 Reserve`.
- Middle group = sub-function or zone (e.g. Switch / Dimming / Status / Position).
- Keep **commands and status in distinct, predictable middle groups** (e.g.
  command in `.../0/...`, feedback in `.../4/...`). The pairing engine matches by
  name tokens, so consistent naming matters more than adjacency.
- Reserve address space in every range; never pack ranges 100%.

## Command / status pairs (the most important rule)
- **Every controllable actuator must have a status object.** A switch needs a
  state GA; a dimmer needs a brightness-state GA; a blind needs position + position
  state. `check_missing_status` flags anything without one.
- HA entities must have a `state_address` (or `*_state_address`) wherever the KNX
  device can report it. No status = HA shows stale/guessed state.

## DPT discipline
- Every GA must have a DPT set. Missing DPT is a hard error (`check_dpt`): HA
  cannot decode it.
- Same logical name → same DPT. Inconsistent DPTs across same-named GAs are a bug.
- Common DPTs: switch `1.001`, status `1.011`, up/down `1.008`, stop `1.010`,
  dimming `3.007`, brightness/position `5.001`, temperature `9.001`, humidity
  `9.007`, CO₂/ppm `9.008`, lux `9.004`, energy kWh `13.013`, power W `14.056`,
  scene `17.001`/`18.001`, HVAC mode `20.102`.

## Naming
- Names encode **zone + function** (e.g. "Kitchen ceiling light switch",
  "Bedroom blind position status"). The status keyword (`status`/`state`/`статус`/
  `Rückmeldung`) is what lets the engine pair feedback to its command.
- No empty names, no duplicates. Main and middle ranges get descriptive names.

## Category separation
Keep these domains in their own ranges and HA platforms: lighting, dimming,
shutters, HVAC, sensors, scenes, energy, diagnostics.

## KNX Secure
- When KNX Data Secure / IP Secure is enabled, secure tunneling needs the **ETS
  Keyring export** (`.knxkeys`). Exports from this tool carry the `Security` flag
  per GA; the keyring itself is handled in ETS/HA, never by this server.

## Typical workflow
1. `load_project` the `.knxproj`.
2. `analyze_all` → fix 🔴 errors in ETS, add missing status GAs.
3. `project_report` → human review.
4. `generate_ets_group_addresses` (xml) → import into ETS for any new GAs.
5. `generate_ha_package` → review YAML → deploy to Home Assistant.
6. Commit every artifact to Git.
