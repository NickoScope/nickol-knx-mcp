# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **Hardened parsing of untrusted `.knxproj` / `.knxprod`** (`safexml.py`). A project file is a
  user-supplied ZIP-of-XML, so both XML and ZIP attack classes apply; every place we open an archive
  or parse XML ourselves now goes through one hardened module. **XML:** a dependency-free reject of any
  `<!DOCTYPE`/`<!ENTITY` (the billion-laughs / XXE vector — legitimate ETS XML never carries one), plus
  `defusedxml` parser-level blocking when installed (added as a dependency). **ZIP:** a pre-flight
  against absolute caps (archive size, entry count, per-member and total decompressed size, compression
  ratio) rejects zip-bombs, member names are checked for path-traversal / absolute paths, and each
  member is read through a streaming cap so a header that under-declares its size still can't exhaust
  memory. Wired into `load_project`, `check_device_parameters` and the app-program parser; on a
  violation callers return a normal `{"error": ...}` rather than a traceback. Still strictly read-only.
  Raised by external security review. `tests/test_safexml.py`.

### Changed

- **Contextual domain classification — a DPT alone no longer decides the domain** (`project.py`,
  `explain.py`, `generate_ha.py`, `policy.py`). A 1-bit switch is domain-agnostic (a light just as
  easily as a pump or an AC), yet the classifier defaulted DPT 1.001 → *lighting*, so "Living room AC
  on/off" came out as lighting and then tripped downstream checks. The domain is now a **combination of
  signals**: an explicit name domain wins; a strong, domain-encoding DPT (shutter 1.008, HVAC-mode
  20.102, temperature 9.001, dimming 3.007) keeps its domain; for a domain-soft DPT (1.001/1.011/5.001)
  the **main group name** disambiguates; with no signal at all a bare 1-bit GA is honestly **unknown**
  rather than a guessed lighting. When an explicit name contradicts a *strong* DPT the result is
  `unknown` (a genuine conflict, surfaced by `explain_ga` as `contested`) — not a silent pick. Matching
  is word-boundary, not substring, so "ac" no longer fires inside "terrace". Name terms broadened
  (English + Russian HVAC incl. `ac`/`a/c`/`air conditioner`, RGB/colour lighting). Verified on three
  real projects: every "AC on/off" is now HVAC; policy taxonomy-outlier **noise fell sharply** (demo
  11→2, one real project 31→6, another 200→57) because `check_policy` now flags only misplaced
  **actuators** (lighting/shutter/HVAC) and treats sensors, scene links, thresholds and timeout
  parameters as the cross-cutting GAs they are. `explain_ga` shows the winning signal and tier; the HA
  generator still emits a switch for a now-HVAC simple on/off, so no device is dropped.

  Dogfooding the classifier against a deliberately messy synthetic house then hardened it further:
  the **main-range name map no longer lets a "middle 0" clobber its main group's name** (both start at
  the same raw address, so the old modulo heuristic overwrote "Освещение" with "Вкл/Выкл" and the
  range rescue silently died — depth in the range tree decides now); a category that comes from a
  **whole-main-group DPT fallback is soft** (a guess by construction — only an exact `(main, sub)`
  table entry is strong), so a vendor enum like 20.609 no longer poses as authoritative HVAC;
  **DPT 1.010 start/stop is soft** (ventilation timers use it too, not just shutters); terms learned:
  Cyrillic **а/с**, **сплит**, **вытяжк**, **яркост** (RU only — EN "brightness" also means weather
  lux), meteo/weather (sensor now outranks hvac so "Метеостанция - Температура" is a sensor, not an
  HVAC actuator). Real-project noise after the round: Minsk 1 outlier / 685 GAs, demo 2 / 239.

### Added

- **Explainable aggregate scores** (`advanced.py`, `handover.py`). Every headline percentage now ships
  the numbers behind it instead of a bare figure: Matter readiness, the completeness grade and
  command/status coverage each carry a `math` block with the numerator, denominator, the exact formula
  (that reproduces the percentage) and, for Matter, the functions **excluded** from the denominator
  because their category has no Matter cluster (previously a silent skip — the biggest source of "why is
  this number what it is?"). The completeness grade also states its band thresholds. A reviewer can now
  audit or reproduce any score. Report-only, additive. Raised by external review. `tests/test_explainable_aggregates.py`.

- **Provenance / confidence** (`explain.py`, new MCP tool `explain_ga`). The enriched model mixes ETS
  facts, DPT-derived structure and name heuristics; downstream tools then treat the result almost like a
  fact. `explain_ga(address)` makes the reasoning auditable for one GA: per decision (category / kind /
  status pairing) it reports the signals that fired with a confidence tier — **authoritative** (an ETS
  Function role) > **structural** (the KNX DPT) > **heuristic** (a name keyword) — and flags **conflicts**
  (e.g. a GA the DPT calls `lighting` while the name says "AC" → `contested`), the hotspot for silent
  misclassification. Additive and read-only (no change to the core model). Asked for by three independent
  reviewers (two external councils + a field integrator). `tests/test_explain.py`. Tool count 27 → 28.

- **Role-aware feedback completeness** (`detect_role_completeness` in `analyze.py`, surfaced through
  `check_missing_status`). "Does the function have *a* status?" was not enough — a dimmer with an on/off
  status but no brightness status silently passed and inflated coverage/Matter scores. The new check
  flags a brightness/position **command** (DPT 5.001) whose device has no matching value **status**
  (`missing_value_status`), using a device-identity match so it does not borrow a sibling's status.
  Closes the demo's own documented limitation — recall on the demo house is now 5/5. Raised by an
  external expert review. `tests/test_role_completeness.py`.

- **Project Policy Profile** (`policy.py`, new MCP tool `check_policy`). Validate a project
  against *its own* agreed rules (main-group taxonomy, naming regex, command/status exemptions)
  instead of one universal "professional standard" — a direct answer to integrator feedback that
  conventions differ per school. With a YAML profile the declared taxonomy is authoritative; with
  **no** profile the taxonomy is **inferred from the project itself** and GAs that deviate from
  their main group's own majority domain are flagged (`policy_taxonomy_outlier`) — never against an
  alien standard. Ships an example profile (`examples/policy-profile.example.yaml`) and
  `tests/test_policy.py`. Tool count 26 → 27.

- **Cross-device parameter QA** (`param_check.py`, new MCP tool `check_device_parameters`).
  Reads per-device `ParameterInstanceRef` values straight from the `.knxproj` project part
  (data xknxproject does not expose), groups identical devices by application program, and
  flags the odd one out: `clear_outliers` (a strong majority with a small minority — e.g. one
  thermostat with a different setpoint/hysteresis, one presence detector with a different
  detection time) and `split_configs` (balanced 2+ variants — review, often two zones).
  Parameter names resolved from the app-program. Findings are ranked by **significance**: a
  `focus` list of *config-value* outliers (setpoint/hysteresis/time/threshold — where an odd device
  is usually a real mistake), separated from mode/type flags and per-room text labels — on a real
  275-device project this turns 422 raw outliers into a 9-item focus (incl. the thermostats whose
  init-setpoint differs from their siblings). Read-only; no ETS/bus; encrypted projects are skipped
  honestly. Validated on real 42–275-device projects; synthetic `tests/test_param_check.py`.
  Community-driven (asked for in Discussions). Tool count 25 → 26.

- **`skills/ha-git-backup`** — an ops-companion skill for the engineer package: a two-circuit
  Home Assistant backup system (real git in `/config` with a deploy key and a pre-commit secret
  scanner + age-encrypted full backups in GitHub Releases), with install/sync/scan/offsite/restore
  scripts, HA automations, a restore runbook and a mandatory monthly drill. Field-tested;
  the secret scanner ships canary-tested (BusyBox `grep -e` lesson recorded).

- **Manufacturer names from the archive itself** (`appprog_parser.py`): `parse_devices_from_project`
  now reads vendor names from the `knx_master.xml` shipped inside every `.knxproj`/`.knxprod`
  (e.g. M-0073 → HDL, M-00B6 → Ekinex S.p.A.) instead of relying on a hardcoded id map that can
  never be complete; the static map remains as fallback.

### Fixed

- **Root-cause suppression (external-review noise).** A GA with an **empty name** has an unreliable
  classification, so it no longer cascades into a `missing_status_address` warning and a
  `policy_taxonomy_outlier` — the single root cause (`empty_name` from `check_naming`) is kept and the
  dependent findings are suppressed. On the demo house the empty `2/5/2` now yields one finding instead
  of three. `tests/test_root_cause.py`.

- **Noise & unsafe repairs surfaced by an external expert review on the demo house.** (1) Scene-control
  GAs (DPT 17/18) are no longer flagged as `missing_status` — they recall a preset and have no single
  state to read back (now `scene_no_status`, INFO), and `suggest_repairs` no longer synthesises a bogus
  boolean status GA for them. (2) Generic group commands (`All blinds down`, `All shutters up`) are now
  recognised as central macros (INFO) like `All lights off`, not missing-status warnings. (3) Synthesised
  repair names match the GA's language — an English project no longer gets a Russian `(статус)`/`Значение
  яркости` suffix. On the demo house this cut `missing_status_address` warnings from ~7 (mostly scenes) to
  the one genuine case. `tests/test_council_fixes.py`.

- **`skills/ha-git-backup`**: `install.sh` now pins `core.sshCommand` + a repo-local `known_hosts`
  so the nightly sync pushes from HA's Core container (was failing `Host key verification failed`).

## [0.8.0] — 2026-07-07

**Lessons from a second field project (a different integrator naming school):** positional
command/status pairing, ref-level application programs, and two detector blind spots. All four
changes were validated against a real 859-GA as-built project.

### Added

- **Positional command/status pairing** (#4, `pairing.py` / `analyze.py`). A widespread naming
  school keeps feedback in a *parallel middle group* (command `1/0/s` ↔ status `1/1/s`) with the
  GA name duplicated 1:1 and no status keyword at all — invisible to lexical pairing.
  `detect_missing_status` now also pairs positionally (same main, same sub, different middle,
  identical name, DPT-compatible) and recognises **self-reporting commands** (the actuator's
  R+T communication object linked to the command GA itself). On the field project this cut
  missing-status warnings from 339 to 89 — the ~90 that are actually real — and reports a
  `status_pairing_summary` info with both counters.
- **Application-program parser v2** (#6, `appprog_parser.py`). Vendors like HDL, Ekinex and
  Creatrol publish object names/DPTs/flags on `<ComObjectRef>` while the base `<ComObject>` is a
  near-empty stub. The parser now merges ref-level data over the base (conservatively: refs only
  fill empty fields; a DPT is taken only when every declaring ref agrees, disagreeing variants are
  recorded as `dpt_variants`, never guessed). Unverified DPTs on the field project's 15 device
  models dropped 4341 → 1167 (−73%). The app-program version is now picked by the **highest
  ApplicationVersion** instead of list position — a stale v16 was being parsed where v18 existed.

### Fixed

- **`main_group_unnamed` read the wrong names** (#3, `analyze.py`): main-group names are now taken
  from the authoritative `group_ranges` (a GA record's `main_name` can carry a middle range's
  name), eliminating both false "unnamed" findings and masked truly-unnamed mains.
- **Completeness grader missed pattern-named ranges** (#5, `advanced.py`): a middle range literally
  called «Сцены» full of plain-named scene GAs now counts as scene evidence — the grader reads
  main/middle range names in addition to GA names (and the scene token matches Russian plural
  forms).
- **Pinned `mcp>=1.10,<2`** — the MCP Python SDK v2 (in alpha) renames
  `mcp.server.fastmcp.FastMCP` to `mcp.server.MCPServer`; without the upper bound a future
  `pip install` would pull v2 and break the server import. Verified against the SDK docs.

## [0.7.0] — 2026-07-02

### Added

- **Exact device decomposition from a local catalog** (`device_library.py`). When the
  `NICKOL_KNX_CATALOG` env var points at a device-library YAML file or directory (schema:
  `library-schema.md`), `decompose_device` now returns the **exact vendor object model**
  (`source: catalog-exact`) — real per-channel blocks, object counts, app-program version and
  first-instance objects with their true DPTs — instead of the generic recipe. Falls back to the
  built-in recipes (`source: recipe-approximate`) for any device not in the catalog, so behaviour
  is unchanged when the env is unset. The catalog itself is vendor-catalog data kept **local** and
  is not shipped with the package. Objects the vendor app-program leaves without a DatapointType
  stay `dpt: null` — never guessed.
- **`parse_devices_from_project` (new MCP tool + `appprog_parser.py`)** — deterministic parser that
  extracts the exact vendor comm-object model from the `M-*` application programs embedded in a
  `.knxproj` / `.knxprod`: per device it reports order number, app-program version, object counts and
  detected per-channel blocks (unit · objects-per-instance · stride), converting `DPST-x-y` → `x.00y`.
  Read-only and PII-safe (reads only vendor catalog data, never the client `P-*/0.xml`). With
  `output_path` it writes a device-library YAML into the workspace — feeding the local catalog above,
  so `parse → catalog → decompose_device (catalog-exact)` is a closed loop. Now **25 MCP tools**.

## [0.6.0] — 2026-07-01

**Completes the roadmap** — the tool now validates, repairs, generates (HA / ETS / handover / IoT),
diffs, grades and drafts acceptance protocols, all design-time & read-only.

### Added — B-tier

- **B2 — climate-correctness review** (`generate_ha.py`). Climate generation now emits an explicit
  review note: controller/operation modes made explicit, setpoint-shift command **and** state paired,
  and a flag raised for any mode object that lacks a corresponding state address.
- **B3 — semantic project diff** (`diffproj.py`, new module; new MCP tools `diff_projects` /
  `diff_loaded`). Compares two `.knxproj` versions and reports added / removed / DPT-changed /
  renamed / security-changed group addresses — a reviewable delta between as-designed revisions.
- **B4 — acceptance test protocol** (`advanced.py`; new MCP tool `generate_test_protocol`).
  Produces a per-function acceptance checklist in Markdown for commissioning sign-off.
- **B5 — Matter readiness** (`advanced.py`; new MCP tool `check_matter`). Reports which functions
  round-trip cleanly to a Matter cluster and which do not.
- **B6 — energy scaffold** (`advanced.py`; new MCP tool `check_energy`). Checks metering / energy
  DPT coverage and scaffolds PV / battery / EVSE structure.

### Added — C-tier

- **C1 — KNX IoT semantic export** (`iot.py`, new module; new MCP tool `generate_knx_iot`).
  Emits a KNX IoT Turtle / RDF skeleton for the project.
- **C2 — naming suggestions** (`advanced.py`; new MCP tool `suggest_names`). Naming-hygiene
  proposals for group addresses that drift from the zone + function convention.
- **C3 — as-built completeness grader** (`advanced.py`; new MCP tool `grade_completeness`).
  Grades a project from bare functional skeleton to as-built, by presence of professional patterns
  (central macros, motion tuning, astro/meteo, monitoring, deep metering, scenes, reserves, debug).

### Added — A-tier quick wins

- **A5 — Areas / voice note** (`generate_ha.py`). Documents that HA Areas and voice assignment are
  UI-only concerns, not derivable from the `.knxproj`.
- **A6 — time/date expose** (`generate_ha.py`). Emits a KNX `expose` block for DPT-19.001 clock
  broadcast so HA can serve time/date to the bus.

## [0.5.0] — 2026-07-01

**From validator to repairer.** Previous releases *flagged* problems in a `.knxproj`; this one
starts *proposing the fix*. The headline is a repair-suggestion engine that turns each finding
into a concrete, reviewable change, alongside two new detectors for gaps that silently break the
Home Assistant layer: relative-only dimmers and actuator-dependent cover behaviour.

### Added
- **B1 — repair-suggestion engine** (`repair.py`, new module; new MCP tool `suggest_repairs`).
  For each finding it proposes a concrete fix rather than only naming the problem: infer a DPT for
  a group address that has none, correct a suspect sub-DPT, synthesise a status/feedback GA in a
  free address slot, or add an absolute-brightness GA for a relative-only dimmer. Suggestions only
  — a human reviews them, and accepted new GAs feed `generate_ets_group_addresses`; the server
  never writes to ETS or the bus. On a real 3646-GA project it produced **145 proposals**: 32
  set-DPT, 1 change-DPT, and 112 synthesised status GAs.
- **A2 — relative-only-dimming detector** (`analyze.py`, `relative_only_dimming` finding). A
  `3.007` relative dimmer with no `5.001` absolute-brightness GA in its zone is flagged, because
  Home Assistant cannot set a brightness level from relative dimming alone.
- **A3 — cover invert / travel-time surfacing** (`generate_ha.py`). The cover review reason is now
  `verify_cover_invert` and carries a note listing the actuator-dependent flags that are *not* in
  the `.knxproj` (`invert_position` / `invert_updown` / `invert_angle`, `travelling_time_up` /
  `travelling_time_down`), plus a warning when a cover's position lacks a state address.

## [0.4.0] — 2026-07-01

**Two new lint dimensions: does the DPT sub-type match what the name promises, and is the
project's KNX Secure posture consistent.** This release adds a conservative sub-DPT sanity
linter and a report-only KNX Data Secure posture summary (no key material ever touched),
plus the itemised QA findings in the handover pack.

### Added
- **A1 — sub-DPT sanity linter** (`analyze.py`, surfaced by `check_dpt` and `analyze_all` as the
  `subdpt_suspect` finding). When a group-address name implies a specific DPT sub-type
  (temperature → `9.001`, power → `14.056`, brightness/position → `5.001`, and similar), the
  linter flags a wrong sub-type or a wrong main type. Multilingual keyword matching, deliberately
  conservative — it only fires when the name is unambiguous, so it does not second-guess correct
  or generic DPTs.
- **A4 — KNX Data Secure posture** (`analyze.py` `secure_posture()`, new MCP tool `check_secure`).
  A report-only summary of the project's security posture: secured vs plaintext GA counts, middle
  groups that mix secure and plaintext objects, and a keyring (`.knxkeys`) handover checklist. It
  reads only the per-GA `Security` flag — no key material is read, derived, or emitted.
- **KNX Secure posture section in the handover pack** — section 5 of `handover.md` is rewritten
  from a flat secure-GA count into the full posture section (counts, mixed-group flag, keyring
  handover checklist), so the as-built deliverable states the security posture explicitly.
- **Itemised QA findings in the handover pack** — section 6 of `handover.md` now lists the
  actual 🔴 errors and 🟡 warnings (address + name, grouped by check), not just totals, so the
  handover doubles as a review checklist. Info-level items (intentional reserves / logic / macros)
  stay collapsed.

## [0.3.0] — 2026-07-01

**Spec→structure: a device library and a design methodology, plus the as-built handover pack.**
This release turns the tool from a `.knxproj` *validator* into a *design* aid: from a project
spec you can now expand each device into its group-address recipe and reason about the whole
structure. Shipped alongside the Track B project handover pack and a set of noise-reduction
refinements, the latter two driven by a second real signed Zennio project (a 3646-GA
multi-vendor villa, 5× larger, no ETS Functions).

### Added
- **Device library + `decompose_device` — one device is not one GA** (`device_library.py`, new
  MCP tools `decompose_device` + `list_device_recipes`). Each actuator channel expands into a
  set of communication objects — command, status, dimming (3.007), absolute value/position
  (5.001), HVAC mode (20.102/20.105), colour (232.600/251.600) — each with its own DPT. Given a
  manufacturer order number, device type or alias (e.g. `ZDIDBDX4`, `dimmer`, `JRA/S`,
  `presence detector`) and a channel count, the tool returns the objects a professional
  typically wires per channel and the total GA count, so a spec/ТЗ device list can be turned
  into a group-address structure. Recipes cover switch, dimmer, RGBW LED, shutter/blind,
  floor-heating, AC gateway, DALI, presence, metering, leak and touch-panel families across
  Zennio + ABB. Recipes are **generic vendor facts** compiled from KNX manufacturer ETS product
  databases and public documentation — the *typical-wired* subset, not the full selectable
  master menu. New regression tests cover the dimmer/shutter/panel/unknown paths.
- **`docs/spec-to-structure.md` — the spec→structure methodology.** Documents the reverse of
  validation (design a group-address structure from a spec), the `decompose_device` pipeline,
  and an honest, measured account of what is reproducible from a spec (~90 %: taxonomy, domains,
  logic structure, command/status pairing, DPT discipline) versus what is not (the exact
  per-device object count — an integrator parameterisation choice that varies 2–9× between
  projects; predict a range, never a false-precise number).
- **`generate_handover_pack` — the as-built commissioning deliverable** (Track B). From a
  read-only `.knxproj` it assembles `handover.md` (equipment inventory by manufacturer,
  group-address map by domain, command/status feedback coverage %, KNX Secure scope, QA state),
  a standalone **`topology.svg`** area/line/device diagram, the full `group-addresses.csv` and
  the `ha-package.yaml`. On the villa: 275 devices across 8 manufacturers, 14 domains, 93 %
  feedback coverage — one command produces the whole handover bundle.
- **Divider/separator scratch detection** — commissioning placeholder names made only of
  punctuation (`---`, `=====`) or a marker wrapped in it (`-----addition------`) now classify
  as `scratch` intent, so a missing DPT on them is an INFO note, not a 🔴 error.
- **Logic-function object awareness** — a typed GA (e.g. 9.x temperature) wired into a Zennio
  `[LF] … Data Entry` container (intentionally type-agnostic, raw 2-byte) surfaces as INFO
  `dpt_on_logic_object` instead of a false `dpt_mismatch_co` warning.
- **Central-macro status tolerance** — all-groups broadcast commands (`Общее …`, `Все группы`,
  `Все шторы - Стоп`) surface as INFO `central_macro_no_status` instead of a
  `missing_status_address` warning, since a fan-out broadcast has no single state to read back.

### Fixed
- **Handover domain names** — the group-address map now reads main/middle range names straight
  from the project's `GroupRanges` instead of `GARecord.main_name`, which the parser could
  mislabel (a middle range's name leaking into the main). Domains now render correctly
  (e.g. `[1] Освещение 1 этаж`, `[5] Климат`) instead of a middle-group name.

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

[Unreleased]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/NickoScope/nickol-knx-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/NickoScope/nickol-knx-mcp/releases/tag/v0.1.0
