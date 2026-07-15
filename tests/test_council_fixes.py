"""Fixes from the external-council review (run on the demo house):
  * scene-control GAs (17/18) must NOT be flagged as missing_status (they have no
    single real state) -> a scene_no_status INFO instead, and no synthesised status;
  * generic group commands like "All blinds down" are central macros (INFO), like
    "All lights off" -> not a missing_status warning;
  * synthesised repair names match the GA's language (no Russian "(статус)" on an
    English project).
"""
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.analyze import detect_missing_status
from nickol_knx_mcp.repair import suggest_repairs


def _ga(addr, name, dmain, dsub):
    return {"name": name, "identifier": f"GA-{addr}", "raw_address": 0, "address": addr,
            "project_uid": None, "dpt": {"main": dmain, "sub": dsub}, "data_secure": False,
            "communication_object_ids": [], "description": "", "comment": ""}


def _proj(gas):
    raw = {"info": {"group_address_style": "ThreeLevel", "schema_version": "21"},
           "group_addresses": gas, "communication_objects": {}, "devices": {},
           "functions": {}, "topology": {}, "group_ranges": {}}
    return build_loaded_from_raw(raw, "t.knxproj")


def main():
    gas = {
        "0/0/1": _ga("0/0/1", "Scene Movie", 18, 1),          # scene -> not missing_status
        "0/1/2": _ga("0/1/2", "All blinds down", 1, 8),       # central macro -> INFO
        "1/0/1": _ga("1/0/1", "Kitchen light on", 1, 1),      # EN switch, no status
        "3/0/1": _ga("3/0/1", "Кухня свет вкл", 1, 1),        # RU switch, no status
    }
    p = _proj(gas)
    ms = {(f["code"], f["address"]) for f in detect_missing_status(p)}

    # scene -> scene_no_status INFO, never missing_status_address
    assert ("scene_no_status", "0/0/1") in ms, ms
    assert ("missing_status_address", "0/0/1") not in ms

    # "All blinds down" -> central macro INFO (was wrongly a warning before)
    assert ("central_macro_no_status", "0/1/2") in ms, ms
    assert ("missing_status_address", "0/1/2") not in ms

    # the plain switches DO still get flagged
    assert ("missing_status_address", "1/0/1") in ms
    assert ("missing_status_address", "3/0/1") in ms

    # repair language matches the GA name; and scenes get no synthesised status
    props = suggest_repairs(p)["proposals"]
    names = {p_["for"]: p_["name"] for p_ in props if p_.get("action") == "add_ga"}
    assert names.get("1/0/1", "").endswith("(status)"), names   # EN
    assert names.get("3/0/1", "").endswith("(статус)"), names   # RU
    assert "0/0/1" not in names, "a scene must not get a synthesised status GA"

    print("test_council_fixes: OK — scenes exempt (scene_no_status, no synth status), "
          "'All blinds down' recognised as central macro, repair suffix matches language.")


if __name__ == "__main__":
    main()
