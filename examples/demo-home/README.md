# Demo House — end-to-end example

A complete, **synthetic** worked example of the whole stack this project targets:

```
demo-home.knxproj   →   nickol-knx-mcp   →   generated/ (report · HA entities · ETS export)
   (KNX design)          (design-time)              ↓
                                            ha-brain/ (Home Assistant smart logic)
```

It exists so you can see real input → real output without needing your own project, and as a
showcase of how the KNX (I/O) and Home Assistant (logic) layers fit together.

## What's here

| Path | What it is |
|---|---|
| `demo-home.knxproj` | The synthetic project: **239 group addresses, 47 ETS Functions**, 13 zones (living w/ fireplace, kitchen, master + 2 kids bedrooms each with ensuite, guest WC, laundry, 2 corridors, staircase). Lighting (switch/dim/CCT/RGBW), underfloor heating + AC, sensors, scenes. |
| `generated/project_report.md` | `project_report` output — inventory + 🔴🟡🔵 findings + HA mapping preview. |
| `generated/home-assistant-knx.yaml` | `generate_ha_package` output — KNX entities (switch/light/cover/binary_sensor/sensor) + a `review` list. **Nothing is dropped silently.** |
| `generated/group-addresses.xml` / `.csv` | `generate_ets_group_addresses` output — ETS-importable. |
| `ha-brain/` | The Home Assistant **smart layer** on top of these entities — circadian lighting, multi-factor climate, presence/season/time logic, statistics. See its own [README](ha-brain/README.md). |

## What the tool found (and the deliberate flaws)

The project **intentionally contains 5 mistakes** so the checks have something to catch — see them
flagged in `generated/project_report.md`:

| # | Planted mistake | Caught? |
|---|---|---|
| 1 | A group address with **no DPT** (`Living room CO2`, 4/2/1) | ✅ `check_dpt` 🔴 |
| 2 | Two GAs with the **same name, different DPT** (`Kitchen temperature`) | ✅ `check_dpt` |
| 3 | A dimmer with an on/off status but **no brightness status** (`Kitchen worktop LED`) | ⚠️ not flagged* |
| 4 | A switch with **no status** at all (`Guest WC ceiling`) | ✅ `check_missing_status` |
| 5 | A GA with an **empty name** (`2/5/2`) | ✅ `check_naming` 🔴 |

\* **Honest limitation surfaced by this very demo:** the missing-status check currently asks
"does this control have *a* status?", not "does it have *each expected* status type?". The Kitchen
dimmer has an on/off status, so it isn't flagged for its missing brightness status. Tracked for a
future release.

Inventory: 239 GAs · 47 Functions · 0 errors that block parsing. The HA generator produced
**19 switches, 13 lights, 6 covers, 13 binary sensors, 63 sensors**, with 18/19 switches getting a
`state_address` paired via ETS Function roles.

## ⚠️ Caveats (please read)

- **Synthetic & generated.** This `.knxproj` was authored programmatically (ETS6 schema
  `project/22`) — not exported from ETS. It parses cleanly with `xknxproject` (the library this
  tool uses) and is intended for **tool validation and demonstration**. It has **not** been
  verified to open in ETS6 itself; a real ETS-authored export is the gold standard for that.
- **The flaws are on purpose.** Do not "fix" them — they are the point.
- **`ha-brain/` is a design demo.** Valid Home Assistant YAML built on best practices, but not
  deployed against a live bus here; entity IDs assume the names `generate_ha_package` produces.
