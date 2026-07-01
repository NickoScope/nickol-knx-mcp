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

# --------------------------------------------------------------------------- #
# Regression (#6): a venetian slat becomes the tilt (move_short) of its blind,
# not a standalone cover; a 1-bit diagnostics alarm is a binary_sensor, not a
# phantom command switch.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: slat tilt + diagnostics alarm ===")
from nickol_knx_mcp.project import build_loaded_from_raw
_raw6 = {"group_addresses": {
    "2/0/0": ga("2/0/0", "Living room blind", 1, 8),
    "2/0/1": ga("2/0/1", "Living room blind slat", 1, 8),
    "2/0/2": ga("2/0/2", "Wind alarm", 1, 1),
}}
_p6 = build_loaded_from_raw(_raw6, "mem")
assert _p6.gas["2/0/2"].ha_platform == "binary_sensor", _p6.gas["2/0/2"].ha_platform
assert _p6.gas["2/0/2"].kind == "sensor", _p6.gas["2/0/2"].kind
_pkg6 = _yaml.safe_load(generate_ha_yaml(_p6)["yaml"].split("\n\n", 1)[1])
_covers6 = _pkg6["knx"].get("cover", [])
assert len(_covers6) == 1, f"expected 1 cover (slat not standalone), got {len(_covers6)}"
assert _covers6[0].get("move_short_address") == "2/0/1", _covers6[0]
assert _pkg6["knx"].get("binary_sensor"), "wind alarm should be a binary_sensor"
print("OK: slat -> blind tilt; wind alarm -> binary_sensor")

# --------------------------------------------------------------------------- #
# Regression (round 2): real-project HA mapping gaps found on yene/DemoCase.
#   A) dimmable light with single-token identity gets BOTH on/off and brightness
#      status (one light entity, no duplicate switch).
#   B) shutter on 1.001 up/down + 1.017 stop still becomes a cover.
#   C) date/time DPTs route to review (manual_datetime), not a silent drop.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: light status pairing + shutter DPT variance + datetime ===")
_raw7 = {"group_addresses": {
    "1/0/0": ga("1/0/0", "HaloX.ON/OFF", 1, 1),
    "1/0/1": ga("1/0/1", "HaloX.VALUE", 5, 1),
    "1/0/2": ga("1/0/2", "HaloX.STATE", 1, 1),
    "1/0/3": ga("1/0/3", "HaloX.STATE%", 5, 1),
    "2/0/0": ga("2/0/0", "Shutter.Foyer.UP/DOWN", 1, 1),
    "2/0/1": ga("2/0/1", "Shutter.Foyer.STOP", 1, 17),
    "4/0/0": ga("4/0/0", "Clock.DateTime", 19, 1),
}}
_p7 = build_loaded_from_raw(_raw7, "mem")
_ha7 = generate_ha_yaml(_p7)
_pkg7 = _yaml.safe_load(_ha7["yaml"].split("\n\n", 1)[1])["knx"]
_lights7 = _pkg7.get("light", [])
assert len(_lights7) == 1, f"expected 1 light, got {_lights7}"
for _k in ("address", "state_address", "brightness_address", "brightness_state_address"):
    assert _k in _lights7[0], f"light missing {_k}: {_lights7[0]}"
assert not any("HaloX" in s["name"] for s in _pkg7.get("switch", [])), "HaloX duplicated as switch"
_covers7 = _pkg7.get("cover", [])
assert len(_covers7) == 1 and _covers7[0].get("move_short_address") == "2/0/1", _covers7
assert any(r["reason"] == "manual_datetime" for r in _ha7["review"]), "datetime not routed to review"
print("OK: full light entity (no dup switch); 1.001/1.017 cover; datetime -> review")

# --------------------------------------------------------------------------- #
# Regression (Track D): GA-intent classification removes real-project NOISE.
# Patterns taken verbatim from a real large Zennio project, where reserve
# spares + internal logic GAs produced ~29 false errors and dozens of false
# missing-status warnings. Non-functional GAs must be reclassified, while a real
# functional problem must STILL be flagged (no over-suppression).
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: GA-intent noise reduction (reserve / logic / scratch) ===")
from nickol_knx_mcp.intent import (
    classify_intent, INTENT_RESERVE, INTENT_LOGIC, INTENT_SCRATCH, INTENT_FUNCTIONAL,
)

# Direct classifier checks on real names.
assert classify_intent("Резерв") == INTENT_RESERVE
assert classify_intent("РЕЗЕРВ") == INTENT_RESERVE
assert classify_intent("Промежуточный результат логики индикации") == INTENT_LOGIC
assert classify_intent("Метеостанция - Запрос температуры") == INTENT_LOGIC
assert classify_intent("суммарный сигнал включения групп света") == INTENT_LOGIC
assert classify_intent("1") == INTENT_SCRATCH
assert classify_intent("Новый групповой адрес") == INTENT_SCRATCH
# divider / separator commissioning scratch (large-villa refinement)
assert classify_intent("-----addition------") == INTENT_SCRATCH
assert classify_intent("---") == INTENT_SCRATCH
assert classify_intent("=====") == INTENT_SCRATCH
assert classify_intent("Kitchen ceiling light switch") == INTENT_FUNCTIONAL
# a real name that merely CONTAINS dashes must stay functional
assert classify_intent("01. Кухня - Свет - Вкл/выкл") == INTENT_FUNCTIONAL

_rawD = {"group_addresses": {
    # reserve spares: no DPT (intentional) + same name, different DPTs
    "0/1/8": ga("0/1/8", "Резерв", None, None),
    "1/2/49": ga("1/2/49", "Резерв", 5, 1),
    "1/2/50": ga("1/2/50", "Резерв", 1, 3),
    # internal logic command with no status (should NOT be flagged)
    "1/1/7": ga("1/1/7", "Промежуточный результат логики индикации", 1, 1),
    "8/0/18": ga("8/0/18", "Метеостанция - Запрос температуры", 1, 17),
    # scratch leftover
    "9/2/0": ga("9/2/0", "1", 1, 1),
    # a REAL functional problem that must survive: missing DPT + missing status
    "3/1/21": ga("3/1/21", "07. Спальня - выход Д СО - порог 2", None, None),
    "1/0/0": ga("1/0/0", "Kitchen ceiling light switch", 1, 1),
}}
_pD = build_loaded_from_raw(_rawD, "mem")
assert _pD.gas["0/1/8"].intent == INTENT_RESERVE
assert _pD.gas["1/1/7"].intent == INTENT_LOGIC

_dptD = detect_dpt_issues(_pD)
_codes = {(f["code"], f["address"]) for f in _dptD}
# reserve with no DPT -> INFO reserve_without_dpt, NOT a missing_dpt error
assert ("reserve_without_dpt", "0/1/8") in _codes, _codes
assert ("missing_dpt", "0/1/8") not in _codes, "reserve wrongly raised a DPT error"
# functional missing DPT still a real error
assert ("missing_dpt", "3/1/21") in _codes, "real missing DPT was suppressed!"
# "Резерв" reused with different DPTs is NOT an inconsistency
assert not any(f["code"] == "inconsistent_dpt" for f in _dptD), "reserve flagged inconsistent_dpt"

_naflD = validate_naming(_pD)
# reserve dupes + scratch short name must not raise naming warnings
assert not any(f["code"] == "duplicate_name" for f in _naflD), "reserve flagged duplicate_name"
assert not any(f["code"] == "name_too_short" for f in _naflD), "scratch '1' flagged name_too_short"

_msD = {f["address"] for f in detect_missing_status(_pD)}
assert "1/1/7" not in _msD, "logic GA wrongly flagged missing_status"
assert "8/0/18" not in _msD, "weather request wrongly flagged missing_status"
assert "9/2/0" not in _msD, "scratch GA wrongly flagged missing_status"
# the real functional switch with no status IS still flagged
assert "1/0/0" in _msD, "real functional command lost its missing-status warning!"
print("OK: reserve/logic/scratch de-noised; real DPT + status problems preserved")

# --------------------------------------------------------------------------- #
# Regression (large-villa refinements): [LF] logic-object DPT + central-macro status.
# From a real 3646-GA villa where (a) typed GAs wired into Zennio "[LF] Data
# Entry" objects produced false DPT-mismatch warnings, and (b) central "Все
# группы"/"Общее" broadcast commands produced false missing-status warnings.
# Both must be downgraded to INFO while REAL mismatches / gaps still warn.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: [LF] logic-object + central-macro de-noise (large villa) ===")

_rawLF = {
    "communication_objects": {
        "CO-LF": {"name": "[LF] (2-Byte) Data Entry 1", "number": 1, "text": "",
                  "function_text": "", "description": "", "device_address": "1.1.9",
                  "device_application": None, "module": None, "channel": None,
                  "dpts": [{"main": 7, "sub": 1}], "object_size": "2 bytes",
                  "group_address_links": ["5/0/0"], "flags": {}, "dpas": None},
        "CO-REAL": {"name": "Operation status", "number": 2, "text": "",
                    "function_text": "", "description": "", "device_address": "1.1.9",
                    "device_application": None, "module": None, "channel": None,
                    "dpts": [{"main": 7, "sub": 1}], "object_size": "2 bytes",
                    "group_address_links": ["6/1/13"], "flags": {}, "dpas": None},
    },
    "group_addresses": {
        # typed temperature GA wired into an [LF] container -> INFO, not warning
        "5/0/0": ga("5/0/0", "01. Холл - АТ - Воздух", 9, 1, co_ids=["CO-LF"]),
        # real bitfield-vs-object mismatch on a normal object -> still a warning
        "6/1/13": ga("6/1/13", "Основная В/У - Статус работы", 237, 600, co_ids=["CO-REAL"]),
    },
}
_lf = detect_dpt_issues(build_loaded_from_raw(_rawLF, "mem"))
_lfc = {(f["code"], f["address"]) for f in _lf}
assert ("dpt_on_logic_object", "5/0/0") in _lfc, _lfc
assert ("dpt_mismatch_co", "5/0/0") not in _lfc, "[LF] object wrongly warned as mismatch"
assert ("dpt_mismatch_co", "6/1/13") in _lfc, "real DPT mismatch was suppressed!"

_rawCM = {"group_addresses": {
    "0/0/1": ga("0/0/1", "Общее освещение - Все группы", 1, 1),   # central macro
    "0/1/0": ga("0/1/0", "Все шторы - Стоп", 1, 10),              # central macro
    "1/0/9": ga("1/0/9", "Гостиная - Бра - Вкл", 1, 1),          # normal cmd, no status
}}
_cm = detect_missing_status(build_loaded_from_raw(_rawCM, "mem"))
_cmc = {(f["code"], f["address"]) for f in _cm}
assert ("central_macro_no_status", "0/0/1") in _cmc, _cmc
assert ("missing_status_address", "0/0/1") not in _cmc, "central macro wrongly warned"
assert ("central_macro_no_status", "0/1/0") in _cmc, _cmc
# a normal command with no status MUST still warn (no over-suppression)
assert ("missing_status_address", "1/0/9") in _cmc, "real missing-status lost!"
print("OK: [LF] objects + central macros de-noised; real mismatches/gaps preserved")

# --------------------------------------------------------------------------- #
# Regression (Track A): colour light assembly + B1 (no borrowed brightness_state)
# + climate assembly. Patterns from the real signed demo / a real Zennio project.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: colour light + B1 status borrow + climate (Track A) ===")

# -- A-colour: dimmable RGBW + colour-temperature light assembles fully --------
_rawC = {"group_addresses": {
    "1/0/3": ga("1/0/3", "Living RGBW accent on/off", 1, 1),
    "1/4/3": ga("1/4/3", "Living RGBW accent status", 1, 11),
    "1/2/3": ga("1/2/3", "Living RGBW accent brightness", 5, 1),
    "1/5/3": ga("1/5/3", "Living RGBW accent brightness status", 5, 1),
    "1/3/3": ga("1/3/3", "Living RGBW accent colour", 251, 600),
    "1/6/3": ga("1/6/3", "Living RGBW accent colour status", 251, 600),
    "1/3/9": ga("1/3/9", "Living RGBW accent colour temperature", 7, 600),
}}
_pC = build_loaded_from_raw(_rawC, "mem")
_haC = generate_ha_yaml(_pC)
_lC = _yaml.safe_load(_haC["yaml"].split("\n\n", 1)[1])["knx"]["light"]
assert len(_lC) == 1, f"expected 1 colour light, got {_lC}"
_e = _lC[0]
for _k in ("address", "state_address", "brightness_address", "brightness_state_address",
           "rgbw_address", "rgbw_state_address", "color_temperature_address"):
    assert _k in _e, f"colour light missing {_k}: {_e}"
assert _e["rgbw_address"] == "1/3/3" and _e["rgbw_state_address"] == "1/6/3", _e
assert _e["color_temperature_mode"] == "absolute", _e
print("OK: RGBW + colour-temp assembled into one light entity")

# -- B1: a light with no own brightness status must NOT borrow a sibling's -----
_rawB = {"group_addresses": {
    "1/2/11": ga("1/2/11", "Kitchen worktop LED brightness", 5, 1),   # no own status
    "1/2/12": ga("1/2/12", "Kitchen island pendants brightness", 5, 1),
    "1/5/12": ga("1/5/12", "Kitchen island pendants brightness status", 5, 1),
}}
_pB = build_loaded_from_raw(_rawB, "mem")
_lB = _yaml.safe_load(generate_ha_yaml(_pB)["yaml"].split("\n\n", 1)[1])["knx"]["light"]
_byname = {l["name"]: l for l in _lB}
_worktop = _byname["Kitchen worktop LED brightness"]
_island = _byname["Kitchen island pendants brightness"]
assert "brightness_state_address" not in _worktop, \
    f"B1 regression: worktop borrowed a status: {_worktop}"
assert _island.get("brightness_state_address") == "1/5/12", _island
print("OK: B1 — worktop took no status; island kept its own (no cross-borrow)")

# -- A-climate: thermostat zone assembles; a mode-only zone goes to review -----
_rawT = {"group_addresses": {
    # full zone -> valid climate
    "3/0/1": ga("3/0/1", "Living floor temperature", 9, 1),
    "3/1/1": ga("3/1/1", "Living floor target temperature", 9, 1),
    "3/2/1": ga("3/2/1", "Living floor target temperature status", 9, 1),
    "3/3/1": ga("3/3/1", "Living floor HVAC mode", 20, 102),
    "3/4/1": ga("3/4/1", "Living floor HVAC mode status", 20, 102),
    "3/6/1": ga("3/6/1", "Living floor valve status", 5, 1),
    # mode-only zone -> review, never an invalid entity
    "3/3/2": ga("3/3/2", "Garage HVAC mode", 20, 102),
}}
_pT = build_loaded_from_raw(_rawT, "mem")
_haT = generate_ha_yaml(_pT)
_cT = _yaml.safe_load(_haT["yaml"].split("\n\n", 1)[1])["knx"].get("climate", [])
assert len(_cT) == 1, f"expected 1 climate, got {_cT}"
_cl = _cT[0]
assert _cl["temperature_address"] == "3/0/1"
assert _cl["target_temperature_state_address"] == "3/2/1"
assert _cl["operation_mode_address"] == "3/3/1"
assert _cl["operation_mode_state_address"] == "3/4/1"
assert _cl["command_value_state_address"] == "3/6/1"
assert any(r["reason"] == "manual_climate" and r["address"] == "3/3/2" for r in _haT["review"]), \
    "mode-only zone should go to review, not emit an invalid climate"
print("OK: full zone -> valid climate; mode-only zone -> review")

# --------------------------------------------------------------------------- #
# Regression (Track B): handover pack assembles a document + valid SVG diagram.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: handover pack (Track B) ===")
from nickol_knx_mcp.handover import build_handover, build_topology_svg

_hp = build_handover(proj)
_hmd = _hp["markdown"]
# all seven sections present
for _sec in ("# KNX Handover Pack", "## 1. Topology", "## 2. Equipment inventory",
             "## 3. Group-address map by domain", "## 4. Command / status coverage",
             "## 5. KNX Secure posture", "## 6. QA state at handover", "## 7. Pack contents"):
    assert _sec in _hmd, f"handover missing section: {_sec}"
# equipment inventory picked up the synthetic MDT device + its order number
assert "MDT" in _hmd and "AKK-0416.03" in _hmd, "device inventory not rendered"
# summary shape
_hs = _hp["summary"]
for _k in ("ga_count", "devices", "manufacturers", "lines", "domains",
           "feedback_coverage_pct", "secure_gas", "errors", "warnings"):
    assert _k in _hs, f"handover summary missing {_k}"
assert _hs["devices"] == 1 and _hs["manufacturers"] == 1, _hs
# valid, standalone SVG
_svg = _hp["svg"]
assert _svg.startswith("<svg") and _svg.rstrip().endswith("</svg>"), "SVG malformed"
assert "KNX topology" in _svg
# it parses as XML (well-formed)
import xml.dom.minidom as _mdom
_mdom.parseString(_svg)
print("OK: handover pack — 7 sections, inventory, summary, well-formed SVG")

# --------------------------------------------------------------------------- #
# Regression: device-library decomposition recipes.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: device-library decompose_device ===")
from nickol_knx_mcp.device_library import decompose_device, list_recipes
_dim=decompose_device("ZDIDBDX4", channels=4)          # DIMinBOX DX4, 4 channels
assert _dim["matched"] and _dim["type"]=="dimmer_channel", _dim
assert any(o["dpt"]=="3.007" for o in _dim["objects"]), "dimmer must expose 3.007 rel-dim"
assert any(o["dpt"]=="5.001" for o in _dim["objects"]), "dimmer must expose 5.001 abs"
assert _dim["total_ga"]==_dim["objects_per_unit"]*4
_sh=decompose_device("JRA/S")                          # ABB shutter alias
assert _sh["type"]=="shutter_channel" and any(o["dpt"]=="1.008" for o in _sh["objects"])
_p=decompose_device("Z50")                             # panel → 0 new GAs
assert _p["type"]=="panel" and _p["objects_per_unit"]==0, "panel should create 0 GAs"
_miss=decompose_device("totally-unknown-xyz")
assert _miss["matched"] is False
assert len(list_recipes())>=10
print("OK: decompose_device — dimmer 3.007+5.001, shutter 1.008, panel=0, unknown handled")

# --------------------------------------------------------------------------- #
# Regression (v0.4.0): A1 sub-DPT linter + A4 KNX Secure posture.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: A1 sub-DPT linter + A4 secure posture ===")
from nickol_knx_mcp.analyze import secure_posture
_rawA1 = {"group_addresses": {
    "5/0/0": ga("5/0/0", "Гостиная - Температура воздуха", 9, 4),   # temp but 9.004(lux) -> suspect
    "5/0/1": ga("5/0/1", "Спальня - Температура", 9, 1),            # correct -> ok
    "1/0/0": ga("1/0/0", "Kitchen brightness value", 5, 10),        # brightness but 5.010 -> suspect
    "1/0/1": ga("1/0/1", "Hall brightness value", 5, 1),           # correct
    "2/0/0": ga("2/0/0", "CO2 living room", 5, 1),                 # co2 (strong) wrong main -> suspect
}}
_sd = {(f["code"], f["address"]) for f in detect_dpt_issues(build_loaded_from_raw(_rawA1, "mem"))}
assert ("subdpt_suspect", "5/0/0") in _sd, "temp 9.004 not caught"
assert ("subdpt_suspect", "1/0/0") in _sd, "brightness 5.010 not caught"
assert ("subdpt_suspect", "2/0/0") in _sd, "co2 wrong-main not caught"
assert ("subdpt_suspect", "5/0/1") not in _sd and ("subdpt_suspect", "1/0/1") not in _sd, "false positive on correct DPT"
print("OK: sub-DPT linter — wrong sub + wrong main caught, correct DPTs clean")

_rawS = {"group_addresses": {
    "1/0/0": ga("1/0/0", "Kitchen switch", 1, 1, secure=True),
    "1/0/1": ga("1/0/1", "Kitchen switch status", 1, 11, secure=False),  # same middle -> mixed
    "2/0/0": ga("2/0/0", "Hall switch", 1, 1, secure=True),
}}
_sp = secure_posture(build_loaded_from_raw(_rawS, "mem"))
assert _sp["secured"] == 2 and _sp["plaintext"] == 1, _sp
assert _sp["keyring_required"] is True
assert len(_sp["mixed_middle_groups"]) >= 1, "mixed secure/plaintext middle not flagged"
assert any("keyring" in s.lower() for s in _sp["checklist"]), "no keyring step"
print("OK: secure posture — counts, mixed-middle flag, keyring checklist")

# --------------------------------------------------------------------------- #
# Regression (v0.5.0): A2 relative-only dimming · A3 cover invert · B1 repairs.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: A2 relative-dim + A3 cover invert + B1 repair engine ===")
from nickol_knx_mcp.repair import suggest_repairs
# A2
_a2raw = {"group_addresses": {
    "1/0/0": ga("1/0/0", "Кухня свет - Относительное диммирование", 3, 7),   # no abs -> flag
    "2/0/0": ga("2/0/0", "Зал свет - Относительное диммирование", 3, 7),
    "2/0/1": ga("2/0/1", "Зал свет - Значение яркости", 5, 1),               # abs present -> ok
}}
_a2 = {(f["code"], f["address"]) for f in detect_dpt_issues(build_loaded_from_raw(_a2raw, "mem"))}
assert ("relative_only_dimming", "1/0/0") in _a2, "relative-only dimmer not flagged"
assert ("relative_only_dimming", "2/0/0") not in _a2, "false positive: zone has abs brightness"
print("OK: A2 — relative-only dimmer flagged; dimmer with absolute brightness clean")
# A3
_a3raw = {"group_addresses": {
    "2/0/0": ga("2/0/0", "Спальня штора - Вверх/вниз", 1, 8),
    "2/1/0": ga("2/1/0", "Спальня штора - Позиция", 5, 1),
}}
_a3 = generate_ha_yaml(build_loaded_from_raw(_a3raw, "mem"))["review"]
assert any(r["reason"] == "verify_cover_invert" and "invert_position" in r.get("note", "") for r in _a3), \
    "cover invert/travel review note missing"
print("OK: A3 — cover surfaces invert/travel flags for review")
# B1
_b1raw = {"group_addresses": {
    "3/0/0": ga("3/0/0", "Спальня свет - Вкл/выкл", None, None),   # missing DPT -> set_dpt
    "4/0/0": ga("4/0/0", "Холл выключатель", 1, 1),               # no status -> add_ga
}}
_r = suggest_repairs(build_loaded_from_raw(_b1raw, "mem"))
_acts = {p["action"] for p in _r["proposals"]}
assert "set_dpt" in _acts, "no set_dpt proposal for missing_dpt"
assert any(p["action"] == "add_ga" and "статус" in p["name"] for p in _r["proposals"]), "no status add_ga"
_sd = [p for p in _r["proposals"] if p["action"] == "set_dpt"][0]
assert _sd["dpt"] == "1.001", _sd
print("OK: B1 — repair engine proposes set_dpt + synthesised status GA")

# --------------------------------------------------------------------------- #
# Regression (v0.6.0): B3 diff · B4 protocol · B5 matter · B6 energy · C1/C2/C3
# + A5 areas / A6 expose.
# --------------------------------------------------------------------------- #
print("\n=== REGRESSION: v0.6.0 advanced (B3/B4/B5/B6/C1/C2/C3 + A5/A6) ===")
from nickol_knx_mcp.advanced import (matter_readiness, completeness_grade,
                                     energy_scaffold, test_protocol, suggest_naming)
from nickol_knx_mcp.diffproj import diff_loaded
from nickol_knx_mcp.iot import generate_knx_iot_turtle
# C3 completeness grade
_cg = completeness_grade(proj)
assert "grade" in _cg and 0 <= _cg["score"] <= 100
# B5 matter readiness
_mr = matter_readiness(proj)
assert "controllable_functions" in _mr and "matter_ready" in _mr
# B6 energy (demo has "Total energy" 13.013)
_en = energy_scaffold(proj)
assert _en["metering_gas"] >= 1 and _en["scaffold"]
# C2 naming (demo has an empty-name GA)
_nm = suggest_naming(proj)
assert _nm["count"] >= 1
# B4 protocol
_tp = test_protocol(proj)
assert "# Functional acceptance protocol" in _tp["markdown"]
# C1 turtle
_tt = generate_knx_iot_turtle(proj)
assert _tt.startswith("@prefix") and "knx:Datapoint" in _tt and "knx:groupAddress" in _tt
# B3 diff
_d1 = {"group_addresses": {"1/0/0": ga("1/0/0", "Light", 1, 1), "1/0/1": ga("1/0/1", "Temp", 9, 1)}}
_d2 = {"group_addresses": {"1/0/0": ga("1/0/0", "Light", 1, 1), "1/0/1": ga("1/0/1", "Temp", 9, 4),
                           "2/0/0": ga("2/0/0", "New GA", 1, 1)}}
_df = diff_loaded(build_loaded_from_raw(_d1, "a"), build_loaded_from_raw(_d2, "b"))
assert _df["added"] == 1 and _df["dpt_changed"] == 1, _df
# A6 expose (datetime GA present)
_ex = generate_ha_yaml(build_loaded_from_raw({"group_addresses": {
    "10/0/0": ga("10/0/0", "System - Date/Time", 19, 1)}}, "mem"))
assert any(r["reason"] == "verify_expose" for r in _ex["review"]), "no time/date expose"
print("OK: v0.6.0 — matter, completeness, energy, naming, protocol, turtle, diff, expose")
