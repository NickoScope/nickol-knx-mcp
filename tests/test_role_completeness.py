"""Role-aware feedback completeness (external-review gap #3): a brightness/position
COMMAND (5.001) with no matching value STATUS must be flagged, even when the device
already has an on/off status. And it must NOT borrow a sibling device's status.
"""
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.analyze import detect_role_completeness, detect_missing_status


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
        # incomplete dimmer: on/off + on/off status + brightness cmd, but NO brightness status
        "1/0/11": _ga("1/0/11", "Kitchen worktop switch", 1, 1),
        "1/2/11": _ga("1/2/11", "Kitchen worktop brightness", 5, 1),
        "1/4/11": _ga("1/4/11", "Kitchen worktop status", 1, 11),
        # complete dimmer: brightness cmd + brightness status
        "1/2/12": _ga("1/2/12", "Living pendant brightness", 5, 1),
        "1/5/12": _ga("1/5/12", "Living pendant brightness status", 5, 1),
        # a shutter position command without position status
        "2/2/1": _ga("2/2/1", "Bedroom blind position", 5, 1),
    }
    p = _proj(gas)
    rc = {f["address"] for f in detect_role_completeness(p)}

    assert "1/2/11" in rc, "incomplete dimmer brightness must be flagged"
    assert "1/2/12" not in rc, "complete dimmer must NOT be flagged"
    assert "2/2/1" in rc, "shutter position command without status must be flagged"

    # must not borrow the sibling's status: worktop is flagged even though 'Living
    # pendant brightness status' exists (different device identity)
    f = next(f for f in detect_role_completeness(p) if f["address"] == "1/2/11")
    assert "brightness" in f["message"] and f["code"] == "missing_value_status"

    # and it surfaces through detect_missing_status (the aggregate the tools use)
    assert any(x["code"] == "missing_value_status" and x["address"] == "1/2/11"
               for x in detect_missing_status(p))

    print("test_role_completeness: OK — brightness/position command without a value "
          "status is flagged (no sibling-status borrowing); complete dimmer stays clean.")


if __name__ == "__main__":
    main()
