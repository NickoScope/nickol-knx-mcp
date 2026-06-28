# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/NickoScope/nickol-knx-mcp/releases/tag/v0.1.0
