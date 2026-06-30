# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-06-30

**Colour/climate entity assembly and GA-intent noise reduction.** Two feature tracks
shipped together, both driven by real ETS projects: full colour-light (RGBW/RGB/CCT) and
KNX `climate` entity generation with a status-pairing (B1) correctness fix, and a GA-intent
classifier that stops intentional non-functional addresses from raising false errors. On a
real 685-GA Zennio project the intent work cut false errors **29 → 6** and missing-status
noise **79 → 45** while preserving all 12 genuine `dpt_mismatch_co` catches.

### Added
- **Colour lights, climate entities and a status-pairing fix** (Track A), driven by the real
  signed demo and a 685-GA Zennio project.
  - **Colour control** is assembled into the `light` entity: RGB (DPT 232.600 →
    `color_address`), RGBW (251.600 → `rgbw_address`), xyY (242.600 → `xyy_address`) and
    absolute colour-temperature (7.600 → `color_temperature_address` + `color_temperature_mode`),
    each with its status, matched to the zone's light by identity. A colour GA with no on/off
    in its zone is routed to review instead of dropped.
  - **Climate** entities are now generated: anchored on an HVAC mode (DPT 20.102/20.105), the
    zone's current temperature (9.001), target-temperature status, operation/controller modes
    and valve `command_value_state` are gathered by location and emitted **only** when the HA-
    required minimum (`temperature_address` + `target_temperature_state_address`) is present —
    otherwise the zone goes to review, so an invalid climate entity is never written. Keys
    verified against the Home Assistant KNX docs. (Real files: demo 6, Zennio 7 climate zones.)
  - **B1 fix — no borrowed status.** A command now only takes a status whose identity nests
    with its own (a shared zone token like "kitchen" is not enough), and a status maps to
    exactly one entity. This stopped "worktop LED" inheriting "island pendants" brightness and
    removed all shared-status addresses on the real files.
  - New DPTs: 232.600 / 251.600 / 242.600 / 7.600 (colour), 20.105 (controller mode), 1.100
    (heat/cool). New regression tests cover colour assembly, the B1 borrow guard and climate
    (valid zone emitted, mode-only zone reviewed).
- **GA-intent classification — noise reduction on real projects** (`intent.py`). Every group
  address is now classified as `functional` / `reserve` / `logic` / `scratch`. Intentional
  non-functional GAs no longer "cry wolf": reserve spares with no DPT become an INFO note
  (`reserve_without_dpt`) instead of a 🔴 error; reserve names repeated across different DPTs
  are not flagged `duplicate_name` / `inconsistent_dpt`; internal logic / virtual signals and
  scratch leftovers are excluded from missing-status warnings. The `dpt_mismatch_co` check and
  every real functional finding are untouched. Driven by a real 685-GA Zennio project where
  this cut false errors **29 → 6** and missing-status noise **79 → 45** while preserving all
  12 real `dpt_mismatch_co` catches. `list_group_addresses`, the report inventory and the
  `analyze_all` summary now expose the intent breakdown. New regression test covers the
  reserve / logic / scratch patterns (and proves real DPT + status problems still surface).
- `docs/` — a self-contained GitHub Pages landing site (project overview, two-layer
  architecture, demo-house stats, an interactive 5-tab dashboard preview, the HA "brain",
  and a call for testers).
- `examples/demo-home/` — a complete synthetic worked example: a 239-GA / 47-Function demo
  `.knxproj`, the tool's generated report + Home Assistant entities + ETS export, and a
  `ha-brain/` Home Assistant smart layer (circadian lighting, multi-factor climate, presence/
  season/time logic, statistics). Includes 5 deliberate mistakes to show the checks (and an
  honest note on the one the missing-status check doesn't yet catch).

## [0.1.2] — 2026-06-28

**Home Assistant mapping quality** — a second hardening pass driven by running the tool
against more public ETS **4.2 / 5.0 / 5.5 / 6** projects (`yene/knxproj` DemoCase,
`tuxedo0801/KnxProjParser`, `dataheld/knxray`, `whaeuser/open-knxviewer`). Three new
regression tests; zero crashes across the whole corpus.

### Added
- **Dimmable lights are assembled completely.** A light now collects BOTH its on/off
  status (1.x) and brightness status (5.x) via identity-based pairing, folds the on/off
  command into the same `light` entity (no more duplicate `switch`), and pairs correctly
  even when the device identity is a single name token (e.g. `HaloSpotLeft.A.VALUE` ↔
  `HaloSpotLeft.A.STATE%`). Switches gained the same identity-based status pairing.
- **Wider shutter detection.** A cover's up/down is recognised on canonical DPT 1.008 *or*
  any 1.x command named up/down (`UP/DOWN`, `auf/ab`); stop is recognised on DPT 1.007 /
  1.010 / 1.017 *or* a "stop"/"stopp"/"стоп" name. Position and stop siblings attach only to
  the same shutter (zone-identity guard), so multiple blinds in one main group no longer
  cross-wire. Real ETS4/5 projects that use 1.001+1.017 now map to full covers.
- **Date / time / text DPTs recognised** (10.001 time, 11.001 date, 19.001 datetime,
  16.000/16.001 string): routed to `review` as `manual_datetime` / `manual_text` (HA KNX has
  dedicated date/time/text platforms) instead of an opaque `unmapped_dpt`.

## [0.1.1] — 2026-06-28

**Hardening release.** Every change below was surfaced by running the tool end-to-end
against **real ETS5/ETS6 project files** (the `XKNX/xknxproject` test fixtures), not the
synthetic smoke test — which alone never exercised the real parser or the MCP server path.
Five new regression tests now guard these cases.

### Fixed
- **Critical:** the `load_project` MCP tool recursed infinitely (`RecursionError`) on
  **every** real `.knxproj`. The server tool function `load_project` shadowed the imported
  project loader of the same name, so it called itself instead of parsing. It now delegates
  to `load_project_file`. This made the tool's primary entry point unusable over MCP; the
  synthetic smoke test missed it because it calls the parser directly, bypassing the server.

### Added
- **ETS Function role pairing — the headline feature — is now actually implemented.**
  command↔status pairs are taken from ETS Function roles (e.g. `SwitchOnOff` ↔ `InfoOnOff`)
  via `pairing.function_status_pairs()`, consumed by both `check_missing_status` and the HA
  generator. Previously Functions were ignored entirely despite the README claiming they
  were the primary signal. Consequences fixed: a feedback GA named only "Status" now pairs
  correctly (name tokens no longer required), HA entities get the right `state_address`, and
  function-paired commands are no longer false-flagged as missing a status.
- **No silent drops in HA generation ("no silent caps").** Every group address is now either
  emitted as an entity or listed in the `review` output; the YAML header reports how many
  need manual review. Previously, GAs the generator could not classify simply vanished.
- **Smarter shutter classification.** German/directional names are recognised (`Behang`,
  `Lamelle`, `auf/ab`, `Raffstore`, `Markise`, plus RU equivalents). A shutter-looking
  command whose DPT lacks a sub-type now gets an actionable `shutter_incomplete_dpt` review
  hint (set 1.008 / 1.010 / 5.001 in ETS) instead of being dropped as "unknown".
- **Venetian slats handled as tilt.** A slat GA (Lamelle / slat / ламель / tilt) is attached
  to its parent blind cover as `move_short_address` instead of becoming a standalone cover;
  an unmatched slat is flagged `shutter_slat_unattached` for manual attachment.
- **Diagnostics alarms are inputs.** A 1-bit diagnostics GA (wind/frost/rain/smoke/leak
  alarm, fault) is now a read-only `binary_sensor` instead of a phantom command switch.

## [0.1.0] — 2026-06-28

Initial public beta.

### Added
- Design-time MCP server with **12 tools**: `load_project`, `list_group_addresses`,
  `get_devices`, `get_topology`, `check_naming`, `check_missing_status`, `check_dpt`,
  `analyze_all`, `generate_ha_package`, `generate_ets_group_addresses`, `project_report`,
  `workspace_info`.
- Read-only `.knxproj` parsing via `xknxproject` (ETS5/ETS6, password-protected supported).
- GA classification (category + kind) from DPT and multilingual (EN/DE/RU) name keywords.
- Naming, missing-status, and DPT validation checks.
- Home Assistant KNX YAML generation with a conservative `review` list for ambiguous items.
- ETS-importable group-address export in XML (`knx.org/xml/ga-export/01`) and CSV.
- Markdown project report.
- Confined-workspace write guarantee (`NICKOL_KNX_WORKSPACE`); no bus access by design.
- `CLAUDE.md` design playbook, end-to-end smoke test (synthetic 16-GA project), example
  Claude Desktop config.

### Known limitations
- Tested end-to-end on a synthetic project only; real-world `.knxproj` testing is ongoing
  (see the call for testers in the README).

[Unreleased]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/NickoScope/nickol-knx-mcp/releases/tag/v0.1.0
