# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/NickoScope/nickol-knx-mcp/releases/tag/v0.1.0
