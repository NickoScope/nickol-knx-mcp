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
        # 1-bit switch (domain-agnostic DPT) named "AC" -> correctly HVAC, NOT a
        # conflict: the DPT does not encode a domain, the name legitimately does.
        "3/2/1": _ga("3/2/1", "Living room AC on/off", 1, 1),
        # strong, domain-encoding DPT (3.007 dimming = lighting) named for another
        # domain ("fan" = hvac) -> a GENUINE conflict -> 'unknown' / contested.
        "3/3/1": _ga("3/3/1", "Bathroom fan", 3, 7),
        "1/0/1": _ga("1/0/1", "Kitchen light switch", 1, 1),    # name-derived lighting command
        "1/4/1": _ga("1/4/1", "Kitchen light status", 1, 11),   # its status
    }
    p = _proj(gas)

    # 1. AC on/off is now correctly HVAC (name over an agnostic DPT), no conflict
    ac = explain_ga(p, "3/2/1")
    assert ac["category"]["value"] == "hvac", ac["category"]
    assert ac["conflicts"] == "none", ac["conflicts"]
    assert ac["confidence"] == "heuristic", ac["confidence"]   # name decided it
    assert any(e["tier"] == "structural" for e in ac["category"]["evidence"])  # DPT still shown
    assert any("hvac" in e["signal"] for e in ac["category"]["evidence"])

    # 2. strong DPT vs name -> genuine conflict, contested, resolved to unknown
    fan = explain_ga(p, "3/3/1")
    assert fan["category"]["value"] == "unknown", fan["category"]
    assert fan["conflicts"] != "none" and any("hvac" in c for c in fan["conflicts"]), fan["conflicts"]
    assert fan["confidence"] == "contested", fan["confidence"]

    # 3. name-derived lighting switch: no conflict, heuristic (name, not the agnostic
    #    DPT), paired to its status by name token
    sw = explain_ga(p, "1/0/1")
    assert sw["category"]["value"] == "lighting", sw["category"]
    assert sw["conflicts"] == "none", sw["conflicts"]
    assert sw["confidence"] == "heuristic", sw["confidence"]
    assert sw["status_pairing"]["paired"] is True
    assert sw["status_pairing"]["method"] == "name_token"
    assert sw["status_pairing"]["status"] == "1/4/1"
    assert sw["status_pairing"]["tier"] == "heuristic"

    # 4. missing address -> error
    assert "error" in explain_ga(p, "9/9/9")

    print("test_explain: OK — AC on/off is HVAC via name over an agnostic DPT (no conflict); "
          "a strong DPT contradicting the name is contested/unknown; name-derived lighting "
          "switch is heuristic + name-token paired; missing address errors.")


if __name__ == "__main__":
    main()
