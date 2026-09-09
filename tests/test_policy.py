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
from nickol_knx_mcp.policy import check_policy, load_policy, example_policy_yaml
import yaml


def _ga(addr, name, dmain, dsub):
    return {"name": name, "identifier": f"GA-{addr}", "raw_address": 0, "address": addr,
            "project_uid": None, "dpt": {"main": dmain, "sub": dsub}, "data_secure": False,
            "communication_object_ids": [], "description": "", "comment": ""}


def _project():
    # main 1: three lighting (1.001) + ONE shutter (1.008) -> the shutter is the deviant
    # main 2: three shutter (1.008) -> consistent
    gas = {
        "1/0/1": _ga("1/0/1", "Kitchen light A", 1, 1),
        "1/0/2": _ga("1/0/2", "Kitchen light B", 1, 1),
        "1/0/3": _ga("1/0/3", "Kitchen light C", 1, 1),
        "1/0/4": _ga("1/0/4", "Odd blind here", 1, 8),   # shutter DPT in the lighting main
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

    # 4. issue #13 (avataru): the example profile must be seeded from THIS project's
    #    main groups — never list mains the project does not have (4..7 here).
    ex = example_policy_yaml(p)
    doc = yaml.safe_load(ex)
    assert doc["main_groups"] == {1: ["lighting"], 2: ["shutter"]}, doc["main_groups"]
    assert doc["reserve"]["expect_range"] is False, "no reserve main -> must not expect one"
    live = [l for l in ex.splitlines() if not l.lstrip().startswith("#")]
    assert not any(l.strip().startswith(("4:", "5:", "6:", "7:")) for l in live), \
        "static default mains leaked into a project-seeded example"
    assert "NOT your project's" in ex, "defaults must be present only as a labelled comment"
    # round-trip: the seeded example is a valid profile and flags the same deviant
    open(path, "w").write(ex)
    res4 = check_policy(p, load_policy(path))
    assert ("policy_domain_mismatch", "1/0/4") in {(f["code"], f["address"]) for f in res4["findings"]}
    os.unlink(path)

    # 5. a main with NO clear majority is written commented-out with its mix, not guessed
    from nickol_knx_mcp.project import build_loaded_from_raw as _b
    raw = {"info": {"project_id": "P-2", "name": 'Quote "Test"', "group_address_style": "ThreeLevel",
                    "schema_version": "21"},
           "group_addresses": {
               "0/0/1": _ga("0/0/1", "Central light", 1, 1), "0/0/2": _ga("0/0/2", "Central blind", 1, 8),
               "0/0/3": _ga("0/0/3", "Central temp", 9, 1), "0/0/4": _ga("0/0/4", "Central light2", 1, 1),
           }, "communication_objects": {}, "devices": {}, "functions": {}, "topology": {},
           "group_ranges": {}}
    p2 = _b(raw, "mixed.knxproj")
    ex2 = example_policy_yaml(p2)
    doc2 = yaml.safe_load(ex2)                      # quotes in the name must not break YAML
    assert not doc2["main_groups"], f"mixed main must not be asserted: {doc2['main_groups']}"
    assert "# 0:" in ex2 and "mixed" in ex2, ex2

    # 6. without a project the default taxonomy is still written, labelled as default
    ex0 = example_policy_yaml(None)
    assert yaml.safe_load(ex0)["main_groups"][7] == ["reserve"] and "DEFAULT" in ex0

    print("test_policy: OK — inferred taxonomy flags the deviant GA vs the project's own "
          "majority; a declared profile is authoritative and changing it changes the findings; "
          "the example profile is seeded from the project's own main groups (issue #13).")


if __name__ == "__main__":
    main()
