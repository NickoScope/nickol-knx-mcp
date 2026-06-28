"""Smoke test the full pipeline against a synthetic KNX project."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.analyze import validate_naming, detect_missing_status, detect_dpt_issues
from nickol_knx_mcp.generate_ha import generate_ha_yaml
from nickol_knx_mcp.generate_ets import generate_ets_csv, generate_ets_xml
from nickol_knx_mcp.report import build_report


def ga(addr, name, main, sub, secure=False, desc="", co_ids=None):
    return {
        "name": name, "identifier": f"GA-{addr}", "raw_address": 0,
        "address": addr, "project_uid": None,
        "dpt": ({"main": main, "sub": sub} if main is not None else None),
        "data_secure": secure, "communication_object_ids": co_ids or [],
        "description": desc, "comment": "",
    }


raw = {
    "info": {
        "project_id": "P-1", "name": "Nikolay Test House",
        "last_modified": "2026-06-01T10:00:00Z", "group_address_style": "ThreeLevel",
        "guid": "x", "created_by": "ETS6", "schema_version": "21",
        "tool_version": "6.3.0", "xknxproject_version": "3.9.0", "language_code": "ru-RU",
    },
    "communication_objects": {
        "CO-1": {"name": "Switch", "number": 1, "text": "", "function_text": "",
                 "description": "", "device_address": "1.1.1", "device_application": None,
                 "module": None, "channel": None, "dpts": [{"main": 1, "sub": 1}],
                 "object_size": "1 bit", "group_address_links": ["1/0/0"],
                 "flags": {"read": False, "write": True, "communication": True,
                           "transmit": False, "update": False, "read_on_init": False},
                 "dpas": None},
    },
    "devices": {
        "1.1.1": {"name": "MDT Switch", "hardware_name": "AKK", "order_number": "AKK-0416.03",
                  "description": "", "manufacturer_name": "MDT", "individual_address": "1.1.1",
                  "application": None, "project_uid": None,
                  "communication_object_ids": ["CO-1"], "channels": {}},
    },
    "topology": {
        "1": {"name": "Area 1", "description": None, "lines": {
            "1.1": {"name": "Line 1", "medium_type": "TP", "description": None,
                    "devices": ["1.1.1"]}}}
    },
    "locations": {},
    "group_addresses": {
        # Lighting: command 1.001 WITH status -> ok
        "1/0/0": ga("1/0/0", "Kitchen light switch", 1, 1, co_ids=["CO-1"]),
        "1/4/0": ga("1/4/0", "Kitchen light status", 1, 11),
        # Lighting: command WITHOUT status -> should flag (different middle from status)
        "1/0/1": ga("1/0/1", "Hall light switch", 1, 1),
        # Dimming light: brightness command + status
        "1/1/0": ga("1/1/0", "Living dimmer brightness", 5, 1),
        "1/4/1": ga("1/4/1", "Living dimmer brightness status", 5, 1),
        # Shutter up/down + stop + position
        "2/0/0": ga("2/0/0", "Bedroom blind up/down", 1, 8),
        "2/0/1": ga("2/0/1", "Bedroom blind stop", 1, 10),
        "2/1/0": ga("2/1/0", "Bedroom blind position", 5, 1),
        "2/4/0": ga("2/4/0", "Bedroom blind position status", 5, 1),
        # Sensors
        "4/0/0": ga("4/0/0", "Living temperature", 9, 1),
        "4/0/1": ga("4/0/1", "Living CO2", 9, 8),
        # Missing DPT -> error
        "5/0/0": ga("5/0/0", "Mystery object", None, None),
        # Empty name -> error
        "5/0/1": ga("5/0/1", "", 1, 1),
        # Duplicate name + inconsistent DPT
        "6/0/0": ga("6/0/0", "Sensor X", 9, 1),
        "6/0/1": ga("6/0/1", "Sensor X", 9, 4),
        # Energy
        "7/0/0": ga("7/0/0", "Total energy", 13, 13),
    },
    "group_ranges": {
        "1": {"name": "Lighting", "address_start": 2048, "address_end": 4095,
              "comment": "", "group_addresses": [], "group_ranges": {
                  "1/0": {"name": "Switch", "address_start": 2048, "address_end": 2303,
                          "comment": "", "group_addresses": ["1/0/0", "1/0/1"], "group_ranges": {}},
              }},
    },
    "functions": {
        "F-1": {"function_type": "SwitchableLight",
                "group_addresses": {
                    "1/0/1": {"address": "1/0/1", "name": "Hall light switch",
                              "project_uid": None, "role": "SwitchOnOff"},
                },
                "identifier": "F-1", "name": "Hall Light", "project_uid": None,
                "space_id": "S-1", "usage_text": ""},
    },
}

proj = build_loaded_from_raw(raw, "/tmp/test.knxproj")
print("=== LOADED ===")
print("GAs:", len(proj.gas), "style:", proj.style)
for a, r in list(proj.gas.items())[:4]:
    print(f"  {a} {r.name!r} dpt={r.dpt} cat={r.category} kind={r.kind} ha={r.ha_platform} mid={r.middle_key}")

print("\n=== NAMING ===")
for f in validate_naming(proj):
    print(" ", f["severity"], f["code"], f["address"], "-", f["message"][:70])

print("\n=== MISSING STATUS ===")
for f in detect_missing_status(proj):
    print(" ", f["severity"], f["code"], f["address"], "-", f["message"][:70])

print("\n=== DPT ISSUES ===")
for f in detect_dpt_issues(proj):
    print(" ", f["severity"], f["code"], f["address"], "-", f["message"][:70])

print("\n=== HA YAML ===")
ha = generate_ha_yaml(proj)
print("counts:", ha["counts"])
print(ha["yaml"])

print("=== ETS CSV ===")
print(generate_ets_csv(proj))

print("=== ETS XML ===")
print(generate_ets_xml(proj))

print("=== REPORT SUMMARY ===")
rep = build_report(proj)
print(rep["summary"])
print("\n--- report head ---")
print("\n".join(rep["markdown"].splitlines()[:30]))

# --------------------------------------------------------------------------- #
# Regression: the MCP server tool `load_project` must delegate to the project
# loader, not call itself (a name-shadowing bug once caused infinite recursion).
# Calling it on a bad path must raise a normal error, never RecursionError.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: server.load_project must not recurse ===")
import nickol_knx_mcp.server as _server
try:
    _server.load_project("/nonexistent/__no_such__.knxproj")
except RecursionError as exc:  # pragma: no cover
    raise AssertionError(
        "server.load_project recursed — load_project name-shadowing regression"
    ) from exc
except Exception as exc:
    print(f"OK: delegated, raised {type(exc).__name__} (expected, not RecursionError)")
else:
    print("OK: delegated (no error)")

# --------------------------------------------------------------------------- #
# Regression: ETS Function roles must pair command <-> status (the headline
# feature). A status GA named only "Status" pairs via the InfoOnOff role even
# though name-token pairing alone would miss it.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: ETS Function role pairing ===")
from nickol_knx_mcp.pairing import function_status_pairs


class _StubProject:
    functions = {
        "F-1": {
            "name": "LivingroomLight",
            "group_addresses": {
                "0/0/1": {"address": "0/0/1", "role": "SwitchOnOff"},
                "0/0/2": {"address": "0/0/2", "role": "InfoOnOff"},
            },
        }
    }
    gas = {"0/0/1": object(), "0/0/2": object()}


_pairs = function_status_pairs(_StubProject())
assert _pairs == {"0/0/1": "0/0/2"}, f"function pairing regression: {_pairs}"
print("OK: SwitchOnOff <-> InfoOnOff paired via ETS Function role")

# --------------------------------------------------------------------------- #
# Regression: HA generation must never drop a GA silently ("no silent caps").
# Every GA is either emitted in an entity or listed in the review.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: HA generation drops nothing silently ===")
import yaml as _yaml
_pkg = _yaml.safe_load(ha["yaml"].split("\n\n", 1)[1]) or {}
_emitted = set()
for _items in (_pkg.get("knx") or {}).values():
    for _it in _items:
        for _k, _v in _it.items():
            if "address" in _k:
                _emitted.add(_v)
_reviewed = {r.get("address") for r in ha["review"]}
_dropped = set(proj.gas) - _emitted - _reviewed
assert not _dropped, f"GAs silently dropped from HA: {sorted(_dropped)}"
print(f"OK: all {len(proj.gas)} GAs accounted for (emitted or in review)")

# --------------------------------------------------------------------------- #
# Regression: German/directional shutter keywords classify as shutter.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: shutter keyword classification ===")
from nickol_knx_mcp.project import _refine_category
for _name in ("Behang D auf/ab", "Lamelle B auf/ab"):
    _cat = _refine_category(_name, "unknown")
    assert _cat == "shutter", f"{_name!r} -> {_cat}, expected shutter"
print("OK: 'Behang/Lamelle auf/ab' classified as shutter")
