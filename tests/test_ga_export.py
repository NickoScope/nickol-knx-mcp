"""GA-export intake, multi-address entity naming, climate setpoint shift.

Fixture mirrors a real TapPlan export (2026-09-13): ga-export/01 namespace, main 0
range starting at 1, DPST tokens, block templates for a dimmable light, a roller
and an RTC. Extended with a setpoint-shift status and the DPT/security variants an
ETS export can carry.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml

from nickol_knx_mcp.ga_export import (GaExportError, load_ga_export, parse_dpt,
                                      read_ga_export_bytes)
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.generate_ha import generate_ha_yaml, _entity_name
from nickol_knx_mcp.generate_ets import generate_ets_xml
from nickol_knx_mcp.analyze import validate_naming, detect_topology_issues, detect_missing_status

XML = b'''<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<GroupAddress-Export xmlns="http://knx.org/xml/ga-export/01">
  <GroupRange Name="Lighting" RangeStart="1" RangeEnd="2047">
    <GroupRange Name="Ground Floor" RangeStart="1" RangeEnd="255">
      <GroupAddress Name="Kitchen Spots On-Off" Address="0/0/6" DPTs="DPST-1-1" />
      <GroupAddress Name="Kitchen Spots On-Off Feedback" Address="0/0/7" DPTs="DPST-1-11" />
      <GroupAddress Name="Kitchen Spots Dimm" Address="0/0/8" DPTs="DPST-3-7" />
      <GroupAddress Name="Kitchen Spots B.Value" Address="0/0/9" DPTs="DPST-5-1" />
      <GroupAddress Name="Kitchen Spots B.Value Feedback" Address="0/0/10" DPTs="DPST-5-1" />
    </GroupRange>
  </GroupRange>
  <GroupRange Name="Shading" RangeStart="2048" RangeEnd="4095">
    <GroupRange Name="Ground Floor" RangeStart="2048" RangeEnd="2303">
      <GroupAddress Name="Bedroom Blind Long Operation" Address="1/0/3" DPTs="DPST-1-8" />
      <GroupAddress Name="Bedroom Blind Short Operation" Address="1/0/4" DPTs="DPST-1-7" />
      <GroupAddress Name="Bedroom Blind Position" Address="1/0/5" DPTs="DPST-5-1" />
      <GroupAddress Name="Bedroom Blind Position Feedback" Address="1/0/6" DPTs="DPST-5-1" />
    </GroupRange>
  </GroupRange>
  <GroupRange Name="Climate" RangeStart="4096" RangeEnd="6143">
    <GroupRange Name="First Floor" RangeStart="4096" RangeEnd="4351">
      <GroupAddress Name="Bedroom Climate Setpoint" Address="2/0/2" DPTs="DPST-9-1" />
      <GroupAddress Name="Bedroom Climate Setpoint Shift" Address="2/0/3" DPTs="DPST-9-2" />
      <GroupAddress Name="Bedroom Climate Setpoint Status" Address="2/0/4" DPTs="DPST-9-1" />
      <GroupAddress Name="Bedroom Climate Actual Temp" Address="2/0/5" DPTs="DPST-9-1" />
      <GroupAddress Name="Bedroom Climate Mode" Address="2/0/6" DPTs="DPST-20-102" />
      <GroupAddress Name="Bedroom Climate Mode Status" Address="2/0/7" DPTs="DPST-20-102" />
      <GroupAddress Name="Bedroom Climate Setpoint Shift Status" Address="2/0/8" DPTs="DPST-9-2" />
      <GroupAddress Name="Hall Secure Temp" Address="2/0/9" DPTs="DPT-9" Security="On" Description="door sensor" />
    </GroupRange>
  </GroupRange>
</GroupAddress-Export>
'''


def _load(data=XML):
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as fh:
        fh.write(data)
        path = fh.name
    try:
        return load_ga_export(path)
    finally:
        os.unlink(path)


def _knx(proj):
    return yaml.safe_load(generate_ha_yaml(proj)["yaml"])["knx"]


# 1. Intake: every GA, DPTs, style, range names, security, description.
p = _load()
assert len(p.gas) == 17, len(p.gas)
assert p.style == "ThreeLevel", p.style
assert p.info["source"] == "ga-export" and p.info["import_warnings"] == []
assert (p.gas["0/0/7"].dpt_main, p.gas["0/0/7"].dpt_sub) == (1, 11)
assert (p.gas["2/0/9"].dpt_main, p.gas["2/0/9"].dpt_sub) == (9, None)
assert p.gas["2/0/9"].data_secure and p.gas["2/0/9"].description == "door sensor"
assert not p.gas["0/0/6"].data_secure
assert not p.devices and not p.functions
print("OK: intake — 17 GAs, ThreeLevel, DPST/DPT tokens, Security, Description")

# 2. Device-less project runs the GA-level checks without inventing device findings.
codes = {f["code"] for f in validate_naming(p)}
assert "ga_style_not_three_level" not in codes, codes
assert detect_topology_issues(p) == []
assert not [f for f in detect_missing_status(p) if f["address"] in ("0/0/9", "1/0/5")]
print("OK: GA-level checks run; no style or topology noise on a GA-only project")

# 3. Naming: entities are named after the shared part of their member names.
knx = _knx(p)
light = knx["light"][0]
cover = knx["cover"][0]
climate = knx["climate"][0]
assert light["name"] == "Kitchen Spots", light
assert (light["address"], light["state_address"], light["brightness_address"],
        light["brightness_state_address"]) == ("0/0/6", "0/0/7", "0/0/9", "0/0/10"), light
assert cover["name"] == "Bedroom Blind", cover
assert climate["name"] == "Bedroom Climate", climate
print("OK: naming — 'Kitchen Spots', 'Bedroom Blind', 'Bedroom Climate'")

# 4. Setpoint shift lands in the climate, with the mode from the DPT, not as a sensor.
assert climate["setpoint_shift_address"] == "2/0/3", climate
assert climate["setpoint_shift_state_address"] == "2/0/8", climate
assert climate["setpoint_shift_mode"] == "DPT9002", climate
assert climate["target_temperature_state_address"] == "2/0/4"
assert climate["temperature_address"] == "2/0/5"
sensor_addrs = {s["state_address"] for s in knx.get("sensor", [])}
assert not sensor_addrs & {"2/0/3", "2/0/8"}, sensor_addrs
print("OK: setpoint shift -> climate setpoint_shift_address/state, mode DPT9002")

# 4b. 6.010 shift gives DPT6010; a 9.002 without the word stays out of the climate.
x610 = XML.replace(b'Address="2/0/3" DPTs="DPST-9-2"', b'Address="2/0/3" DPTs="DPST-6-10"') \
          .replace(b'Address="2/0/8" DPTs="DPST-9-2"', b'Address="2/0/8" DPTs="DPST-6-10"')
assert _knx(_load(x610))["climate"][0]["setpoint_shift_mode"] == "DPT6010"
noword = XML.replace(b"Setpoint Shift Status", b"Delta Status").replace(b"Setpoint Shift", b"Delta")
c2 = _knx(_load(noword))["climate"][0]
assert "setpoint_shift_address" not in c2 and "setpoint_shift_mode" not in c2, c2
print("OK: 6.010 -> DPT6010; a bare 9.002 without a shift word is not taken as a shift")

# 5. Naming guards.
assert _entity_name("Spot 1 Brightness", ["Spot 1 Brightness", "Spot 12 Status"]) == "Spot 1 Brightness"
assert _entity_name("Licht Küche Wert", ["Licht Küche Wert", "RM Licht Küche"]) == "Licht Küche Wert"
assert _entity_name("Kitchen Light", ["Kitchen Light"]) == "Kitchen Light"
assert _entity_name("Kanal A Helligkeit", ["Kanal A Helligkeit", "Kanal A Schalten"]) == "Kanal A"
assert _entity_name("Status: Wert", ["Status: Wert", "Status: Schalten"]) == "Status: Wert"
# Shapes seen on real projects (anonymised). Trim only function words; anything that
# names the room, the device or its type stays, even when the names diverge early.
assert _entity_name("01. Hall - All Blinds - Move", ["01. Hall - All Blinds - Move", "01. Hall blinds stop"]) \
    == "01. Hall - All Blinds - Move"
assert _entity_name("ch1 long door", ["ch1 long door", "ch1 short door"]) == "ch1 long door"
assert _entity_name("06. Bath/Convector - Mode", ["06. Bath/Convector - Mode", "06. Bath temperature"]) \
    == "06. Bath/Convector - Mode"
assert _entity_name("28. Living - A/C - Mode", ["28. Living - A/C - Mode", "28. Living - A/C - Mode status"]) \
    == "28. Living - A/C - Mode"
assert _entity_name("01. Hall - FH - HVAC", ["01. Hall - FH - HVAC", "01. Hall temperature"]) == "01. Hall - FH - HVAC"
assert _entity_name("Kitchen ceiling - Absolute dimming", ["Kitchen ceiling - Absolute dimming",
                                                           "Kitchen ceiling - On"]) == "Kitchen ceiling"
assert _entity_name("Garage gate left - Open/Close", ["Garage gate left - Open/Close",
                                                      "Garage gate left - Stop"]) == "Garage gate left"
assert _entity_name("Living room blind up/down", ["Living room blind up/down",
                                                  "Living room blind position"]) == "Living room blind"
# Collision: two lights whose common prefix would be the same name keep their anchors.
two = XML.replace(b"</GroupRange>\n  </GroupRange>\n  <GroupRange Name=\"Shading\"", b'''
      <GroupAddress Name="Kitchen Spots B.Value Left" Address="0/0/20" DPTs="DPST-5-1" />
      <GroupAddress Name="Kitchen Spots On-Off Left" Address="0/0/21" DPTs="DPST-1-1" />
    </GroupRange>
  </GroupRange>
  <GroupRange Name="Shading"''', 1)
names = sorted(e["name"] for e in _knx(_load(two))["light"])
assert len(names) == len(set(n.lower() for n in names)), names
print("OK: naming guards — digit identity kept, no common prefix, no identity, collisions")

# 6. Round trip: our own ETS export reads back to the same GAs and DPTs.
back = build_loaded_from_raw(read_ga_export_bytes(generate_ets_xml(p).encode("utf-8"), "rt"), "rt")
assert set(back.gas) == set(p.gas)
for a, g in p.gas.items():
    assert (back.gas[a].dpt_main, back.gas[a].dpt_sub, back.gas[a].name) == (g.dpt_main, g.dpt_sub, g.name), a
print("OK: generate_ets_xml -> load_ga_export round trip keeps every GA, name and DPT")

# 7. Hostile and malformed input is refused with a plain error, and warnings are never silent.
for bad, why in [
    (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><GroupAddress-Export/>', "DTD"),
    (b"<Project/>", "root"),
    (b"<GroupAddress-Export", "malformed"),
    (b'<GroupAddress-Export xmlns="http://knx.org/xml/ga-export/01">' + b'<GroupRange Name="x">' * 2000
     + b'</GroupRange>' * 2000 + b"</GroupAddress-Export>", "nesting bomb"),
]:
    try:
        _load(bad)
    except GaExportError:
        pass
    else:
        raise AssertionError(f"accepted {why}")
w = _load(b'''<GroupAddress-Export xmlns="http://knx.org/xml/ga-export/01">
  <GroupAddress Name="a" Address="1/0/1" DPTs="DPST-1-1" />
  <GroupAddress Name="dup" Address="1/0/1" DPTs="DPST-1-1" />
  <GroupAddress Name="bad" Address="99/9/999" />
  <GroupAddress Name="weird" Address="1/0/2" DPTs="foo" />
</GroupAddress-Export>''')
assert set(w.gas) == {"1/0/1", "1/0/2"}
assert len(w.info["import_warnings"]) == 3, w.info["import_warnings"]
assert parse_dpt("DPST-1-1 DPST-1-11") == {"main": 1, "sub": 1} and parse_dpt(None) is None
try:
    load_ga_export("/nonexistent/x.xml")
except GaExportError:
    pass
else:
    raise AssertionError("missing file accepted")
print("OK: DTD, wrong root, malformed, nesting bomb and missing files refused; duplicates/invalid/unknown DPT warned")

print("\nALL GA-EXPORT / NAMING / SETPOINT-SHIFT TESTS PASSED")
