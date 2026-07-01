# nickol-knx-mcp

**A design-time KNX / ETS6 assistant exposed as an [MCP](https://modelcontextprotocol.io) server.**

It reads your `.knxproj` and **validates** it (naming · DPT & sub-DPT · command↔status · KNX Secure · Matter-readiness), **repairs** it (proposes concrete fixes — infers DPTs, synthesises missing status GAs), **decomposes devices** into their group-address recipes, **diffs** two project versions, **grades** completeness, and **generates** Home Assistant YAML, ETS-importable exports (XML/CSV), an as-built **handover pack**, an acceptance test protocol and a KNX IoT semantic export — all **without ever touching the live KNX bus.**

[![CI](https://github.com/NickoScope/nickol-knx-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/NickoScope/nickol-knx-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Status: beta](https://img.shields.io/badge/status-beta-orange.svg)](#-status--call-for-testers)
[![Live demo](https://img.shields.io/badge/live%20demo-online-brightgreen?logo=homeassistant&logoColor=white)](https://nickoscope.github.io/nickol-knx-mcp/)
[![Join the discussion](https://img.shields.io/badge/💬_join_the-discussion-8957e5?logo=github&logoColor=white)](https://github.com/NickoScope/nickol-knx-mcp/discussions/1)
[![nickol-knx-mcp MCP server](https://glama.ai/mcp/servers/NickoScope/nickol-knx-mcp/badges/score.svg)](https://glama.ai/mcp/servers/NickoScope/nickol-knx-mcp)
[![Case study](https://img.shields.io/badge/📐_case_study-spec_PDF_→_KNX_(96%25)-0b3d2e)](docs/case-study.md)

🇷🇺 **Русская версия:** [README.ru.md](README.ru.md)

---

<p align="center">
  <a href="https://nickoscope.github.io/nickol-knx-mcp/">
    <img src="docs/assets/banner.svg" alt="nickol-knx-mcp — live interactive demo and dashboard" width="100%">
  </a>
</p>

<h3 align="center">🎬 <a href="https://nickoscope.github.io/nickol-knx-mcp/">Explore the live interactive demo &amp; dashboard&nbsp;→</a></h3>

> **New — a whole demo house.** [`examples/demo-home`](examples/demo-home) ships a synthetic
> **239-GA / 47-Function** project, the tool's generated report + Home Assistant config + ETS export, and a
> full smart-home **“brain”** — circadian lighting, an **8-factor climate setpoint**, a presence/season/time
> state machine and statistics — driving a **5-view dashboard**. See it all on the
> **[live site&nbsp;↗](https://nickoscope.github.io/nickol-knx-mcp/)**.

---

## 🖥️ The dashboard — live in Home Assistant

Real screenshots from a live Home Assistant running the demo house. They show the tool's assembled
entities at work: **RGBW / RGB / CCT colour lights**, **six floor-heating climate zones** (target, mode
and valve %), a **circadian** lighting curve and a **computed** climate setpoint — not set by hand.

<p align="center">
  <img src="docs/assets/screenshots/overview.png" alt="Overview — home mode, comfort gauge, scenes, climate snapshot" width="78%">
</p>

| Climate | Lighting |
|:---:|:---:|
| [<img src="docs/assets/screenshots/climate.png" alt="Climate view" width="100%">](docs/assets/screenshots/climate.png) | [<img src="docs/assets/screenshots/lighting.png" alt="Lighting view" width="100%">](docs/assets/screenshots/lighting.png) |
| **Energy & stats** | **Presence** |
| [<img src="docs/assets/screenshots/energy.png" alt="Energy view" width="100%">](docs/assets/screenshots/energy.png) | [<img src="docs/assets/screenshots/presence.png" alt="Presence view" width="100%">](docs/assets/screenshots/presence.png) |

▶ **[Explore it interactively on the live site →](https://nickoscope.github.io/nickol-knx-mcp/)** · config in [`examples/demo-home/ha-brain`](examples/demo-home/ha-brain)

---

## 🧪 Status & call for testers

This is a **public beta**. The full pipeline passes an end-to-end smoke test on a synthetic
16-group-address project, but it has had **limited testing against real-world `.knxproj` files** —
and real ETS projects are wonderfully messy and diverse.

**👉 If you have an ETS5/ETS6 project, please try it and tell us what happens.** Open a
[Real-project test report](https://github.com/NickoScope/nickol-knx-mcp/issues/new?template=real_project_test.yml)
issue. The tool is read-only and never connects to a bus, so testing is safe (see
[Safety model](#-safety-model)). See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

💬 **[Join the discussion →](https://github.com/NickoScope/nickol-knx-mcp/discussions/1)** — say hi, ask anything, or share what the tool found on your project.

---

## Why this exists

As of mid-2026 there is **no off-the-shelf ETS6 ↔ Claude / MCP tool**. The KNX community has
been explicitly asking for an integration that can inspect and help modify projects (adding /
renaming devices and group addresses) through an AI/CLI workflow. This package fills exactly the
**design-time** layer — the missing one.

The recommended full setup is four layers; only one needs to be built from scratch:

| Layer | Purpose | What to use | Build it? |
|-------|---------|-------------|-----------|
| 1. Live | states, control, debugging a running house | **official Home Assistant MCP Server** + KNX (XKNX) integration | No, already exists |
| 2. **Design-time** | parse `.knxproj`, validate DPT/naming/status + GA-intent de-noise, generate HA YAML (colour lights + climate assembled) & ETS XML/CSV | **`nickol-knx-mcp` (this package)** | **YES — this is the gap** |
| 3. Files + Git | YAML/CSV/XML, versioning the address schema | standard filesystem + git MCP servers | No, already exists |
| 4. Skill | design rules (GA structure, naming, DPT, scenes) | `CLAUDE.md` in this package | No, included |

> **Safety by design:** layer 2 (this server) **physically cannot** connect to a bus. It has no
> network/bus dependency at all — it only reads `.knxproj` and writes files into a confined
> workspace. The "never write to a live bus" requirement is enforced **structurally**, not by
> promise. Any real interaction with the house goes only through layer 1 (Home Assistant).

---

## What the server does

- **Parses** password-protected ETS5/ETS6 `.knxproj` files via [`xknxproject`](https://github.com/XKNX/xknxproject) (3.9.x).
- **Extracts** group addresses, DPTs, devices, topology, descriptions, and ETS Functions.
- **Classifies** every GA: category (lighting / shutter / hvac / sensor / scene / energy /
  diagnostics) and kind (command / status / sensor) — from the DPT plus multilingual (EN/DE/RU)
  keywords in the name.
- **Validates naming** against a 3-level structure and a configurable regex.
- **Finds missing status addresses** — primarily from ETS Function roles, falling back to
  name-token pairing (command in `…/0/…`, feedback in `…/4/…` is common, so it matches by name
  tokens rather than by middle-group adjacency).
- **Catches DPT problems**: missing DPT, mismatch between a Communication Object and its GA, and
  the same logical name carrying different DPTs.
- **Classifies GA purpose to cut noise** — every group address is tagged `functional` / `reserve` /
  `logic` / `scratch`. Intentional non-functional GAs (spare "Reserve" placeholders, internal logic
  signals, scratch leftovers) are kept out of the error and missing-status checks, so the report
  doesn't cry wolf on real projects (e.g. a 685-GA Zennio project: false errors 29 → 6).
- **Generates Home Assistant KNX YAML** — category by category, conservatively: covers →
  **colour / dimmable lights** → switches → **climate** → sensors/binary. Multi-address entities are
  **assembled**: lights gather on/off + brightness + **RGBW / RGB / colour-temperature** + their
  statuses; `climate` entities gather current temp, target-temp status, operation/controller mode and
  valve command-value (emitted only when the HA-required keys are present, else sent to review).
  Ambiguous items (e.g. DPT 5.001 — brightness vs blind position) are **not guessed**; they go into a
  `review` list instead.
- **Generates ETS-importable** group addresses in **XML** (the recommended `knx.org/xml/ga-export/01`
  schema) and **CSV** (ETS's native layout).
- **Writes a Markdown report** (inventory + 🔴🟡🔵 findings + HA-mapping preview + next steps) for
  human review **before** any import.

**Beyond validation — the design & repair layer (v0.3–v0.6):**

- **Repairs, not just flags** (`suggest_repairs`) — for every finding it proposes a concrete fix:
  infer a DPT from the name, correct a suspect sub-DPT, synthesise a status GA in a free slot, add an
  absolute-brightness GA. Suggestions only; accepted GAs feed the ETS export.
- **Device library** (`decompose_device`) — a KNX actuator channel is not one GA; each channel expands
  into command/status/dimming/position/mode objects. Given an order number or type it returns the
  decomposition recipe (Zennio + ABB families) so a spec/ТЗ device list becomes a GA structure.
- **As-built handover pack** (`generate_handover_pack`) — equipment inventory, group-address map by
  domain, command↔status coverage %, KNX Secure posture + keyring checklist, itemised QA and a
  standalone topology SVG, in one command.
- **Sub-DPT sanity, KNX Secure posture, Matter-readiness, energy-domain** checks; a **semantic project
  diff**, a **completeness grade** (skeleton vs as-built), an **acceptance test-protocol** draft, and a
  **KNX IoT (Turtle/RDF)** semantic export.
- Design methodology: [`docs/spec-to-structure.md`](docs/spec-to-structure.md) — reconstruct a
  group-address structure from a project spec (~90 % of the taxonomy/logic is reproducible; the exact
  per-device object count is the integrator's parameterisation).

All writes go only into the workspace directory (`NICKOL_KNX_WORKSPACE`, default `./knx-workspace`);
writes outside it are rejected.

---

## Installation

Requires **Python 3.10+**.

```bash
git clone https://github.com/NickoScope/nickol-knx-mcp.git
cd nickol-knx-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Dependencies: `mcp>=1.10`, `xknxproject>=3.8`, `PyYAML>=6.0`.

> On Debian/Ubuntu, if pip complains about an externally-managed environment, use a venv (as above)
> or `pip install -e . --break-system-packages`. If `PyJWT` conflicts, run
> `pip install mcp --ignore-installed PyJWT` first.

Verify:

```bash
python tests/test_pipeline.py     # synthetic 16-GA project, end-to-end smoke test
nickol-knx-mcp                    # start the MCP server (stdio)
```

---

## Connecting to Claude

### Claude Desktop

`examples/claude_desktop_config.json` wires up nickol-knx + filesystem + git + home-assistant.
Minimal fragment (macOS config path: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "nickol-knx": {
      "command": "nickol-knx-mcp",
      "env": { "NICKOL_KNX_WORKSPACE": "/path/to/your/knx-workspace" }
    }
  }
}
```

### Claude Code

```bash
claude mcp add nickol-knx \
  -e NICKOL_KNX_WORKSPACE="$HOME/knx-workspace" \
  -- /absolute/path/to/.venv/bin/nickol-knx-mcp
```

Then drop `CLAUDE.md` into your project root — it acts as an ETS Assistant skill (design rules,
safety rules, 3-level GA structure, command/status pairing, DPT discipline, naming, KNX Secure
keyring handling, and the recommended workflow).

---

## MCP tools (24)

**Read**
| Tool | Purpose |
|------|---------|
| `load_project(path, password?, language?)` | parse a `.knxproj` (read-only) and cache it |
| `list_group_addresses(category?, kind?)` | list GAs with classification and filters |
| `get_devices()` | devices + their communication objects |
| `get_topology()` | topology (areas / lines / devices) |

**Validate**
| Tool | Purpose |
|------|---------|
| `check_naming(name_regex?)` | validate naming / 3-level structure |
| `check_missing_status()` | actuators lacking a status object |
| `check_dpt()` | missing / inconsistent DPTs **+ sub-DPT sanity** (temp→9.001, power→14.056…) |
| `check_secure()` | KNX Data Secure posture + keyring handover checklist |
| `check_matter()` | Matter-readiness lint (which functions round-trip to a Matter cluster) |
| `check_energy()` | metering/energy DPT check + PV/battery/EVSE scaffold |
| `analyze_all(name_regex?)` | run every check at once |

**Repair & design**
| Tool | Purpose |
|------|---------|
| `suggest_repairs()` | **propose fixes, not just flag** — infer DPTs, synthesise status/brightness GAs |
| `suggest_names()` | naming-hygiene suggestions |
| `decompose_device(order_number, channels?)` | device → group-address decomposition recipe |
| `list_device_recipes()` | the built-in device library (Zennio + ABB families) |
| `grade_completeness()` | grade a project: bare skeleton vs as-built |
| `diff_projects(path_a, path_b, …)` | semantic diff between two `.knxproj` versions |

**Generate**
| Tool | Purpose |
|------|---------|
| `generate_ha_package(output_path?)` | HA KNX YAML (colour + climate + expose) + review list |
| `generate_ets_group_addresses(fmt="xml"\|"csv", output_path?)` | ETS-importable GAs |
| `generate_handover_pack(output_dir?)` | as-built handover: inventory, GA map, coverage, Secure, QA, topology.svg |
| `generate_test_protocol(output_path?)` | functional acceptance protocol (command → expected status) |
| `generate_knx_iot(output_path?)` | KNX IoT semantic export (Turtle/RDF) |
| `project_report(output_path?, name_regex?)` | Markdown report |
| `workspace_info()` | workspace path + safety guarantees |

---

## Typical workflow

1. `load_project` → point it at your `.knxproj` (+ password if protected).
2. `analyze_all` or `project_report` → read the findings; **human review first**.
3. Fix naming/DPT/status in ETS (by importing generated GAs or manually).
4. `generate_ets_group_addresses(fmt="xml")` → import the missing GAs into ETS.
5. `generate_ha_package` → place the YAML into Home Assistant; resolve `review` items by hand.
6. Keep everything (`.knxproj` export, HA configs, address schema) in Git.
7. Touch the live house only through the Home Assistant MCP (layer 1).

---

## Limitations (honest)

- command/status and category classification is a **heuristic** (DPT + names + ETS Functions). On
  messy projects with no Functions and non-standard names, false negatives/positives are possible —
  which is why the report is always for human review, and ambiguity goes to `review`, not into config.
- DPT 5.001 is structurally ambiguous (brightness vs position); it's disambiguated by keywords —
  double-check with non-standard naming.
- The HA generator is conservative: it would rather defer an item to `review` than emit a wrong entity.
- The server never writes to the bus and never talks to ETS directly — ETS exchange is file
  import/export of GAs only.
- **Tested only on a synthetic project so far.** Real `.knxproj` files vary a lot — hence the
  [call for testers](#-status--call-for-testers).

---

## 🔒 Safety model

- **No bus access, structurally.** There is no networking or bus library in the dependency tree.
  `workspace_info()` reports `bus_access: false`.
- **Read-only on your project.** `project.py` is the only module that touches `.knxproj`, and it
  only reads.
- **Confined writes.** All output is constrained to `NICKOL_KNX_WORKSPACE`; paths outside it are rejected.
- **Human-in-the-loop.** Generate a `project_report` and review it **before** importing into ETS or
  deploying into Home Assistant.

Found a security issue? See [SECURITY.md](SECURITY.md).

---

## Package layout

```
nickol-knx-mcp/
├── nickol_knx_mcp/
│   ├── dpt_map.py        # DPT → category / kind / HA platform / value_type
│   ├── project.py        # the ONLY module that reads .knxproj (read-only)
│   ├── pairing.py        # command↔status pairing by name tokens
│   ├── analyze.py        # naming / missing-status / DPT checks
│   ├── generate_ha.py    # Home Assistant KNX YAML generation
│   ├── generate_ets.py   # ETS XML + CSV generation
│   ├── report.py         # Markdown report
│   └── server.py         # FastMCP server, 24 tools, confined writes
├── tests/test_pipeline.py
├── examples/claude_desktop_config.json
├── CLAUDE.md             # ETS Assistant skill / playbook
├── pyproject.toml
└── README.md
```

---

## Contributing

Testers and contributors are very welcome — especially **real-project test reports**. See
[CONTRIBUTING.md](CONTRIBUTING.md) and the [issue templates](.github/ISSUE_TEMPLATE).

## License

[MIT](LICENSE) © 2026 Nikolay Miroshnichenko

> Not affiliated with or endorsed by the KNX Association. "KNX" and "ETS" are trademarks of the
> KNX Association cc. This is an independent, community tool.
