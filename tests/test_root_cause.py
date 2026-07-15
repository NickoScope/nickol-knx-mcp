"""Root-cause suppression (external-review noise): a GA with an empty name has an
unreliable classification, so it must NOT cascade into missing_status and policy
taxonomy findings — the single root cause is `empty_name` (check_naming).
"""
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.analyze import validate_naming, detect_missing_status
from nickol_knx_mcp.policy import check_policy, load_policy


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
    # main 2 is a clear shutter zone; an empty-name 5.001 command sits in it
    gas = {
        "2/0/1": _ga("2/0/1", "Blind A up/down", 1, 8),
        "2/0/2": _ga("2/0/2", "Blind B up/down", 1, 8),
        "2/0/3": _ga("2/0/3", "Blind C up/down", 1, 8),
        "2/5/2": _ga("2/5/2", "", 5, 1),   # EMPTY name, 5.001 command
    }
    p = _proj(gas)

    naming = {f["code"] for f in validate_naming(p) if "2/5/2" in str(f.get("address", ""))}
    status = [f for f in detect_missing_status(p) if "2/5/2" in str(f.get("address", ""))]
    policy = [f for f in check_policy(p, load_policy())["findings"]
              if "2/5/2" in str(f.get("address", ""))]

    assert "empty_name" in naming, naming                 # the single root cause is kept
    assert status == [], f"empty-name GA must not cascade to missing_status: {status}"
    assert policy == [], f"empty-name GA must not cascade to policy taxonomy: {policy}"

    # sanity: a NAMED command in the same setup is still checked
    gas["2/0/9"] = _ga("2/0/9", "Blind D up/down", 1, 8)
    p2 = _proj(gas)
    assert any(f["address"] == "2/0/9" for f in detect_missing_status(p2)), \
        "named command must still be flagged for missing status"

    print("test_root_cause: OK — empty-name GA yields only empty_name; no missing_status / "
          "policy cascade; named GAs still checked.")


if __name__ == "__main__":
    main()
