"""Test the Project Policy Profile checker (check_policy / load_policy).

Two modes:
  * inferred (no profile) — taxonomy is derived from the project's own majority
    per main group; a GA that deviates from its main group's own domain is flagged
    as ``policy_taxonomy_outlier`` (never against an external "standard").
  * declared (profile) — the profile's main-group taxonomy is authoritative;
    a misfiled GA is flagged as ``policy_domain_mismatch``. Changing the profile
    changes what is flagged.
"""
import os
import tempfile

from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.policy import check_policy, load_policy


def _ga(addr, name, dmain, dsub):
    return {"name": name, "identifier": f"GA-{addr}", "raw_address": 0, "address": addr,
            "project_uid": None, "dpt": {"main": dmain, "sub": dsub}, "data_secure": False,
            "communication_object_ids": [], "description": "", "comment": ""}


def _project():
    # main 1: three lighting (1.001) + ONE shutter (1.008) -> the shutter is the deviant
    # main 2: three shutter (1.008) -> consistent
    gas = {
        "1/0/1": _ga("1/0/1", "Kitchen A", 1, 1),
        "1/0/2": _ga("1/0/2", "Kitchen B", 1, 1),
        "1/0/3": _ga("1/0/3", "Kitchen C", 1, 1),
        "1/0/4": _ga("1/0/4", "Odd one here", 1, 8),   # shutter DPT in the lighting main
        "2/0/1": _ga("2/0/1", "Zone one", 1, 8),
        "2/0/2": _ga("2/0/2", "Zone two", 1, 8),
        "2/0/3": _ga("2/0/3", "Zone three", 1, 8),
    }
    raw = {
        "info": {"project_id": "P-1", "name": "PolicyTest", "group_address_style": "ThreeLevel",
                 "schema_version": "21"},
        "group_addresses": gas, "communication_objects": {}, "devices": {},
        "functions": {}, "topology": {}, "group_ranges": {},
    }
    return build_loaded_from_raw(raw, "policy_test.knxproj")


def main():
    p = _project()

    # 1. inferred (no profile): main 1 is 3/4 lighting -> the shutter GA 1/0/4 is an outlier
    r = load_policy()
    assert r["_source"] == "default"
    res = check_policy(p, r)
    assert res["taxonomy_source"] == "inferred from the project", res["taxonomy_source"]
    codes = {(f["code"], f["address"]) for f in res["findings"]}
    assert ("policy_taxonomy_outlier", "1/0/4") in codes, res["findings"]
    # the consistent shutter main (2) produces no outlier
    assert not any(f["address"].startswith("2/") for f in res["findings"]), res["findings"]

    # 2. declared profile via YAML: main 1 = lighting, main 2 = shutter -> same deviant, but as
    #    an authoritative domain mismatch
    prof = ("name: my-policy\nmain_groups:\n  1: [lighting]\n  2: [shutter]\n")
    fd, path = tempfile.mkstemp(suffix=".yaml"); os.close(fd)
    open(path, "w").write(prof)
    pol = load_policy(path)
    assert pol["_source"] == "profile" and pol["main_groups"][1] == ["lighting"]
    res2 = check_policy(p, pol)
    assert res2["taxonomy_source"] == "declared profile"
    codes2 = {(f["code"], f["address"]) for f in res2["findings"]}
    assert ("policy_domain_mismatch", "1/0/4") in codes2, res2["findings"]

    # 3. change the profile -> main 1 = shutter now -> the THREE lighting GAs become mismatches
    prof2 = ("name: alt\nmain_groups:\n  1: [shutter]\n  2: [shutter]\n")
    open(path, "w").write(prof2)
    pol2 = load_policy(path)
    res3 = check_policy(p, pol2)
    bad = {f["address"] for f in res3["findings"] if f["code"] == "policy_domain_mismatch"}
    assert {"1/0/1", "1/0/2", "1/0/3"} <= bad, bad
    assert "1/0/4" not in bad  # shutter GA now conforms
    os.unlink(path)

    print("test_policy: OK — inferred taxonomy flags the deviant GA vs the project's own "
          "majority; a declared profile is authoritative and changing it changes the findings.")


if __name__ == "__main__":
    main()
