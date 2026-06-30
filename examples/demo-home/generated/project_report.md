# KNX Project Report — Nikolay Demo House

- **Source:** `examples/demo-home/demo-home.knxproj`
- **GA style:** ThreeLevel
- **ETS tool version:** 6.1.5686.0  (xknxproject 3.9.0)
- **Last modified:** 2026-06-28T10:00:00Z


## 1. Inventory

- Group addresses: **239**
- Devices: **0**
- Functions: **47**
- Without DPT: **1**
- KNX Data Secure GAs: **0**


**By category:** diagnostics=10, energy=2, hvac=77, lighting=106, scene=4, sensor=13, shutter=26, unknown=1

**By kind:** command=104, sensor=53, status=81, unknown=1


## 2. Findings

Totals: 🔴 errors **2**, 🟡 warnings **10**, 🔵 info **0**


### 2.1 Naming & structure  (2)

- 🔴 `2/5/2` — Group address has no name.
- 🟡 `4/0/2, 4/0/22` — Name used by 2 group addresses: ['4/0/2', '4/0/22'].


### 2.2 Missing status addresses  (8)

- 🟡 `1/0/50` — Function 'Guest WC ceiling' (FT-1) has command GAs but no status/feedback GA.
- 🟡 `0/0/1` — Command 'Scene All off' (DPT 18.001, Scene control) has no status/feedback GA. Home Assistant cannot read real state.
- 🟡 `0/0/2` — Command 'Scene Movie' (DPT 18.001, Scene control) has no status/feedback GA. Home Assistant cannot read real state.
- 🟡 `0/0/3` — Command 'Scene Night' (DPT 18.001, Scene control) has no status/feedback GA. Home Assistant cannot read real state.
- 🟡 `0/0/4` — Command 'Scene Away' (DPT 18.001, Scene control) has no status/feedback GA. Home Assistant cannot read real state.
- 🟡 `0/1/1` — Command 'All lights off' (DPT 1.001, Switch on/off) has no status/feedback GA. Home Assistant cannot read real state.
- 🟡 `0/1/2` — Command 'All blinds down' (DPT 1.008, Up/Down) has no status/feedback GA. Home Assistant cannot read real state.
- 🟡 `2/5/2` — Command '' (DPT 5.001, Scaling 0-100% (brightness/position)) has no status/feedback GA. Home Assistant cannot read real state.


### 2.3 DPT consistency  (2)

- 🔴 `4/2/1` — 'Living room CO2' has no DPT assigned. Home Assistant requires a DPT to decode this group address.
- 🟡 `4/0/2, 4/0/22` — Group addresses sharing name 'Kitchen temperature' use different DPTs: ['9.001', '9.002'].


## 3. Home Assistant mapping preview

Entities that can be generated now: switch **19**, light **13**, cover **6**, climate **6**, binary_sensor **13**, sensor **41**.


**Needs manual review (50):**

- `0/1/2` All blinds down — verify_cover_mapping
- `2/0/1` Living room window blind up/down — verify_cover_mapping
- `2/0/2` Living room terrace blind up/down — verify_cover_mapping
- `2/0/10` Master bedroom blind up/down — verify_cover_mapping
- `2/0/20` Kids room 1 blind up/down — verify_cover_mapping
- `2/0/30` Kids room 2 blind up/down — verify_cover_mapping
- `0/1/1` All lights off — switch_without_status
- `1/0/50` Guest WC ceiling switch — switch_without_status
- `3/1/9` Guest WC HVAC mode — manual_climate
- `3/1/10` Laundry HVAC mode — manual_climate
- `3/1/11` Corridor GF HVAC mode — manual_climate
- `3/1/12` Corridor UF HVAC mode — manual_climate
- `0/0/1` Scene All off — manual_scene
- `0/0/2` Scene Movie — manual_scene
- `0/0/3` Scene Night — manual_scene
- `0/0/4` Scene Away — manual_scene
- `3/1/7` Kids room 2 HVAC mode — manual_climate
- `3/1/8` Kids bath 2 HVAC mode — manual_climate
- `3/1/21` Living room AC mode — manual_climate
- `3/1/22` Kitchen AC mode — manual_climate
- `3/1/23` Master bedroom AC mode — manual_climate
- `3/1/25` Kids room 1 AC mode — manual_climate
- `3/1/27` Kids room 2 AC mode — manual_climate
- `1/1/2` Living room cove dim — not_mapped
- `1/1/3` Living room RGBW accent wall dim — not_mapped
- `1/1/11` Kitchen worktop LED dim — not_mapped
- `1/1/12` Kitchen island pendants dim — not_mapped
- `1/1/20` Master bedroom ceiling dim — not_mapped
- `1/1/21` Master bedroom bedside left dim — not_mapped
- `1/1/22` Master bedroom bedside right dim — not_mapped
- `1/1/26` Master bath mirror CCT dim — not_mapped
- `1/1/30` Kids room 1 ceiling dim — not_mapped
- `1/1/31` Kids room 1 RGB accent dim — not_mapped
- `1/1/40` Kids room 2 ceiling dim — not_mapped
- `1/1/65` Staircase LED steps dim — not_mapped
- `2/3/1` Living room window blind slat — shutter_slat_unattached
- `2/3/10` Master bedroom blind slat — shutter_slat_unattached
- `3/3/21` Living room AC fan speed — not_mapped
- `3/3/22` Kitchen AC fan speed — not_mapped
- `3/3/23` Master bedroom AC fan speed — not_mapped
- `3/3/25` Kids room 1 AC fan speed — not_mapped
- `3/3/27` Kids room 2 AC fan speed — not_mapped
- `3/6/3` Master bedroom floor valve status — not_mapped
- `3/6/7` Kids room 2 floor valve status — not_mapped
- `3/6/8` Kids bath 2 floor valve status — not_mapped
- `3/6/9` Guest WC floor valve status — not_mapped
- `3/6/10` Laundry floor valve status — not_mapped
- `3/6/11` Corridor GF floor valve status — not_mapped
- `3/6/12` Corridor UF floor valve status — not_mapped
- `4/2/1` Living room CO2 — not_mapped


## 4. Next steps

1. Resolve 🔴 errors (missing DPT, empty names) in ETS first.
2. Add status/feedback GAs for every flagged command.
3. Re-run this report until errors are clear.
4. Generate ETS CSV/XML and HA YAML, commit to Git, then import into ETS and deploy to Home Assistant.
