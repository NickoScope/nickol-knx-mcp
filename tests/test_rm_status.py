"""Regression: a DPT-5.001 shutter position feedback named "… RM" (Rückmeldung,
the German-market status abbreviation) must be recognised as the cover's position
STATUS — not misclassified as a standalone lighting/light entity (issue #12, field
data by Kris1166).

Two layers were broken and are both covered here:
  * classification — the RM GA sits in a shutter ETS Function (blank role) but a
    bare DPT 5.001 with no shutter keyword fell to the lighting default; Function
    membership now promotes it to `shutter`;
  * status recognition — "RM"/"FB" is a whole trailing token the substring
    keywords ("rm "/"rm_") and the stopword tokenizer both dropped, so it read as
    a command; `name_is_status` now recognises it, so it wires as the cover's
    `position_state_address` (a status), never a `position_address` (a command).

Negative guard: a genuine LIGHT brightness feedback named "… RM" that is NOT in a
shutter Function must stay `light` — the promotion is Function-scoped, not a
blanket "RM ⇒ shutter".
"""
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.generate_ha import generate_ha_yaml
from nickol_knx_mcp.analyze import detect_missing_status
import yaml


def _ga(addr, name, dm, ds):
    return {"name": name, "identifier": f"G{addr}", "raw_address": 0, "address": addr,
            "project_uid": None, "dpt": {"main": dm, "sub": ds}, "data_secure": False,
            "communication_object_ids": [], "description": "", "comment": ""}


def _fn(name, *addr_roles):
    return {"name": name, "group_addresses": {a: {"address": a, "role": r} for a, r in addr_roles}}


def _build():
    gas, fns = {}, {}
    # Window shutter: RM status IS in the per-channel function (blank role); move
    # carries MoveUpDown. This is the 26/29 case that was misclassified as light.
    gas["2/1/26"] = _ga("2/1/26", "Zone18 Fenster Bewegen", 1, 8)
    gas["2/2/26"] = _ga("2/2/26", "Zone18 Fenster Schritt/Stop", 1, 7)
    gas["2/3/26"] = _ga("2/3/26", "Zone18 Fenster RM", 5, 1)
    fns["FN-Fenster-26"] = _fn("Fenster", ("2/1/26", "MoveUpDown"),
                               ("2/2/26", "StopStepUpDown"), ("2/3/26", ""))
    # Awning: today it is "accidentally" rescued by the "Markise" keyword — it must
    # still resolve to the cover's position status, now for the RIGHT reason.
    gas["2/1/50"] = _ga("2/1/50", "MarkiseZone1 Bewegen", 1, 8)
    gas["2/2/50"] = _ga("2/2/50", "MarkiseZone1 Schritt/Stop", 1, 17)
    gas["2/3/50"] = _ga("2/3/50", "MarkiseZone1 RM", 5, 1)
    fns["FN-Markise-1"] = _fn("Markise Z1", ("2/1/50", ""), ("2/2/50", ""), ("2/3/50", ""))
    # NEGATIVE: a real light with a brightness feedback named "RM", NOT in a
    # shutter function — must stay a light, RM is its brightness state.
    gas["1/0/0"] = _ga("1/0/0", "Küche Licht schalten", 1, 1)
    gas["1/1/0"] = _ga("1/1/0", "Küche Licht Helligkeit", 5, 1)
    gas["1/3/0"] = _ga("1/3/0", "Küche Licht RM", 5, 1)
    # NEGATIVE 2 (gate-1 audit): a blank-role light GA that shares a heterogeneous
    # shutter Function must NOT be promoted — its explicit light domain wins.
    gas["2/1/60"] = _ga("2/1/60", "Zone20 Rollladen Bewegen", 1, 8)
    gas["2/2/60"] = _ga("2/2/60", "Living Room Light On", 1, 1)   # stray light in a shutter fn
    fns["FN-Mixed-60"] = _fn("Mixed", ("2/1/60", "MoveUpDown"), ("2/2/60", ""))
    # RESIDUAL (Kris re-test 2026-09-04, 15/29): actuator-level Functions carry BLANK
    # or raw-GUID roles — no role token anywhere — yet hold a 1.008 move. The RM
    # must still promote: a shutter Function is recognised by its up/down MOVE, not
    # only by a role string. Step/stop is 1.017 here (what the actuator emits).
    gas["2/1/0"] = _ga("2/1/0", "Zone01 Fenster Bewegen", 1, 8)
    gas["2/2/0"] = _ga("2/2/0", "Zone01 Fenster Schritt/Stop", 1, 17)
    gas["2/3/0"] = _ga("2/3/0", "Zone01 Fenster RM", 5, 1)
    fns["FN-guid-0"] = _fn("Fenster", ("2/1/0", "a1b2-guid"), ("2/2/0", "c3d4-guid"),
                           ("2/3/0", ""))
    gas["2/1/6"] = _ga("2/1/6", "Zone02 kl. Fenster Bewegen", 1, 8)
    gas["2/2/6"] = _ga("2/2/6", "Zone02 kl. Fenster Schritt/Stop", 1, 7)
    gas["2/3/6"] = _ga("2/3/6", "Zone02 kl. Fenster RM", 5, 1)
    fns["FN-blank-6"] = _fn("Fenster", ("2/1/6", ""), ("2/2/6", ""), ("2/3/6", ""))
    # ANOMALY 2/3/1 (explained): the move HAS a role, the step/stop is DPT 1.009
    # ("Enable" — the reporter's own modeling slip, not a step DPT). The RM promotes
    # via the move's role while the 1.009 step/stop honestly stays unknown.
    gas["2/1/1"] = _ga("2/1/1", "Zone16 Fenster Bewegen", 1, 8)
    gas["2/2/1"] = _ga("2/2/1", "Zone16 Fenster Schritt/Stop", 1, 9)
    gas["2/3/1"] = _ga("2/3/1", "Zone16 Fenster RM", 5, 1)
    fns["FN-anom-1"] = _fn("Fenster", ("2/1/1", "MoveUpDown"), ("2/2/1", ""), ("2/3/1", ""))
    # NEGATIVE 3 (LLM-council): a DPT-5.001 scene-recall COMMAND (blank role, neutral
    # name) sharing a shutter Function must NOT become a cover — it is not a position
    # STATUS, so promotion must skip it even though the Function is a shutter one.
    gas["2/1/70"] = _ga("2/1/70", "Zone30 Rollladen Bewegen", 1, 8)
    gas["2/2/70"] = _ga("2/2/70", "Zone30 Rollladen Schritt/Stop", 1, 7)
    gas["2/4/70"] = _ga("2/4/70", "Zone30 Szene Abruf", 5, 1)   # 5.001 COMMAND, not status
    fns["FN-Scene-70"] = _fn("Rollladen70", ("2/1/70", "MoveUpDown"),
                             ("2/2/70", "StopStepUpDown"), ("2/4/70", ""))

    raw = {"info": {"group_address_style": "ThreeLevel", "schema_version": "21"},
           "group_addresses": gas, "communication_objects": {}, "devices": {},
           "functions": fns, "topology": {},
           "group_ranges": {"2": {"address_start": 4096, "name": "Beschattung",
                                  "group_ranges": {}}}}
    return build_loaded_from_raw(raw, "rm-status.knxproj")


def main():
    p = _build()

    # 1. Classification: each shutter RM GA is category=shutter, kind=status.
    for a in ("2/3/26", "2/3/50"):
        g = p.gas[a]
        assert g.category == "shutter", f"{a}: category {g.category!r}, expected shutter"
        assert g.kind == "status", f"{a}: kind {g.kind!r}, expected status"
    # negative: the LIGHT's RM stays lighting (not promoted — not a shutter function)
    assert p.gas["1/3/0"].category == "lighting", p.gas["1/3/0"].category
    assert p.gas["1/3/0"].kind == "status", "a light's RM is still a status"
    # negative 2: a stray light inside a heterogeneous shutter function stays lighting
    assert p.gas["2/2/60"].category == "lighting", \
        f"stray light in a shutter fn was over-promoted: {p.gas['2/2/60'].category}"
    # residual: blank / GUID-role Functions still promote their RM via the 1.008 move,
    # and the 1.017 step/stop promotes too (the cover builder treats 1.017 as a stop).
    for a in ("2/3/0", "2/3/6"):
        assert p.gas[a].category == "shutter" and p.gas[a].kind == "status", \
            f"{a}: blank/GUID-role Function RM not promoted: {p.gas[a].category}/{p.gas[a].kind}"
    assert p.gas["2/2/0"].category == "shutter", "1.017 step/stop in a blank-role fn must promote"
    # anomaly: RM promotes via the move's role; the 1.009 (Enable) step/stop stays unknown.
    assert p.gas["2/3/1"].category == "shutter", "anomaly RM 2/3/1 must promote"
    assert p.gas["2/2/1"].category != "shutter", "a 1.009 'Enable' is not a step DPT — stays as-is"
    # negative 3: a 5.001 scene-recall COMMAND in a shutter function is NOT promoted
    # (only a 5.001 position STATUS is), while the step/stop 2/2/70 still is.
    assert p.gas["2/4/70"].category != "shutter", \
        f"a 5.001 scene-recall command was over-promoted to shutter: {p.gas['2/4/70'].category}"
    assert p.gas["2/2/70"].category == "shutter", "the step/stop in the same fn must promote"

    doc = yaml.safe_load(generate_ha_yaml(p)["yaml"])
    covers = {c["move_long_address"]: c for c in doc.get("knx", {}).get("cover", []) or []}
    lights = {l.get("address"): l for l in doc.get("knx", {}).get("light", []) or []}

    # 2. Each cover gets its RM GA as position_state — and the RM GA is NOT a light.
    assert covers["2/1/26"].get("position_state_address") == "2/3/26", covers["2/1/26"]
    assert covers["2/1/50"].get("position_state_address") == "2/3/50", covers["2/1/50"]
    # residual: blank / GUID-role covers get their RM as position_state too (end-to-end)
    assert covers["2/1/0"].get("position_state_address") == "2/3/0", covers["2/1/0"]
    assert covers["2/1/6"].get("position_state_address") == "2/3/6", covers["2/1/6"]
    assert covers["2/1/1"].get("position_state_address") == "2/3/1", covers["2/1/1"]
    light_addrs = {a for l in lights.values() for a in
                   (l.get("address"), l.get("state_address"), l.get("brightness_address"),
                    l.get("brightness_state_address"))}
    assert "2/3/26" not in light_addrs, "the shutter RM was wired as a light"
    assert "2/3/50" not in light_addrs, "the awning RM was wired as a light"

    # 3. negative: the real light still exists and uses its RM as brightness state.
    assert "1/0/0" in lights, "the genuine light disappeared"

    # 4. no false 'missing status' for the covers whose RM status now pairs.
    miss = {f["address"] for f in detect_missing_status(p)
            if f.get("code") == "missing_status_address"}
    assert "2/1/26" not in miss and "2/1/50" not in miss, f"false missing-status: {miss}"

    print("test_rm_status: OK — '… RM' shutter feedback classifies as shutter/status and "
          "wires as the cover's position_state (issue #12); a light's RM stays a light.")


if __name__ == "__main__":
    main()
