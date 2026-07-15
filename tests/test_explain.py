"""explain_ga — provenance / confidence for one GA (evidence + conflict + pairing tier)."""
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.explain import explain_ga


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
        "3/2/1": _ga("3/2/1", "Living room AC on/off", 1, 1),   # DPT lighting, name hvac -> conflict
        "1/0/1": _ga("1/0/1", "Kitchen light switch", 1, 1),    # clean lighting command
        "1/4/1": _ga("1/4/1", "Kitchen light status", 1, 11),   # its status
    }
    p = _proj(gas)

    # 1. conflict surfaced + confidence contested
    ac = explain_ga(p, "3/2/1")
    assert ac["category"]["value"] == "lighting"
    assert ac["conflicts"] != "none" and any("hvac" in c for c in ac["conflicts"]), ac["conflicts"]
    assert ac["confidence"] == "contested", ac["confidence"]
    assert any(e["tier"] == "structural" for e in ac["category"]["evidence"])

    # 2. clean lighting switch: no conflict, structural evidence, paired to its status by name token
    sw = explain_ga(p, "1/0/1")
    assert sw["conflicts"] == "none", sw["conflicts"]
    assert sw["confidence"] == "structural", sw["confidence"]
    assert sw["status_pairing"]["paired"] is True
    assert sw["status_pairing"]["method"] == "name_token"
    assert sw["status_pairing"]["status"] == "1/4/1"
    assert sw["status_pairing"]["tier"] == "heuristic"

    # 3. missing address -> error
    assert "error" in explain_ga(p, "9/9/9")

    print("test_explain: OK — AC on/off flagged as name/DPT conflict (contested); clean "
          "switch is structural + name-token paired to its status; missing address errors.")


if __name__ == "__main__":
    main()
