"""P7b explainable aggregates: every headline percentage (Matter readiness,
completeness grade, feedback coverage) must ship the numbers behind it — the
denominator, the exact formula, and what was excluded — so a reviewer can
reproduce it instead of trusting a bare number. The Matter denominator in
particular silently dropped functions with no Matter cluster; that exclusion is
now stated.
"""
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.advanced import matter_readiness, completeness_grade
from nickol_knx_mcp.handover import _feedback_coverage
from nickol_knx_mcp.analyze import detect_missing_status


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
    # two lighting commands (one with status), plus a SCENE command that has no
    # Matter cluster -> must be excluded from the Matter denominator, not silently.
    gas = {
        "1/0/1": _ga("1/0/1", "Kitchen light switch", 1, 1),
        "1/4/1": _ga("1/4/1", "Kitchen light status", 1, 11),
        "1/0/2": _ga("1/0/2", "Hall light switch", 1, 1),      # no status
        "0/0/1": _ga("0/0/1", "Evening scene", 17, 1),          # scene -> no Matter cluster
    }
    p = _proj(gas)

    # --- Matter readiness ---
    m = matter_readiness(p)
    assert "math" in m, "matter_readiness must expose a math block"
    math = m["math"]
    # denominator must be the 2 lighting commands, numerator the 1 with status
    assert math["denominator"] == 2, math
    assert math["numerator"] == 1, math
    assert math["pct"] == m["ready_pct"] == 50, (math, m["ready_pct"])
    assert "50%" in math["formula"], math["formula"]
    # the scene must be visibly excluded, not dropped
    exc = math.get("excluded_from_denominator")
    assert exc and exc["controllable_functions_without_a_matter_cluster"] >= 1, exc
    assert "scene" in {k for k in exc["by_category"]}, exc

    # --- Completeness grade ---
    g = completeness_grade(p)
    gm = g["math"]
    assert gm["denominator"] == 8 and gm["pct"] == g["score"], gm
    assert "bands" in gm and "as-built grade" in gm["bands"], gm
    assert gm["formula"].endswith(f"{g['score']}%"), gm["formula"]

    # --- Feedback coverage (handover) ---
    missing = detect_missing_status(p)
    cov = _feedback_coverage(p, missing)
    # 2 lighting commands + the scene command is functional too -> commands counts
    # all functional command GAs; formula must reproduce the pct exactly
    assert cov["with_status"] + cov["missing"] == cov["commands"], cov
    assert f"{cov['pct']}%" in cov["formula"], cov

    # --- empty project: ratio undefined, no crash, formula says so ---
    empty = matter_readiness(_proj({}))
    assert empty["ready_pct"] == 0 and "undefined" in empty["math"]["formula"], empty["math"]

    print("test_explainable_aggregates: OK — Matter/completeness/coverage each ship a "
          "reproducible formula + denominator; Matter states its excluded (no-cluster) "
          "functions; empty project is undefined, not a crash.")


if __name__ == "__main__":
    main()
