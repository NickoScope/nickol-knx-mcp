"""Regression: generate_ha_package must pair every cover to ITS OWN step/stop
(move_short) and position status — never cross-wire, never drop its own — across
the three ETS Function structures a real ETS 6 project actually contains.

Field data by Kris1166 (issue #11), captured with `explain_ga` on the live tool
and mirrored here 1:1 (room names anonymised to RoomA/B/C; compass group names
kept). Three structures, all present in one project:

  A. Per-channel ETS Function, a generic type-only display name ("Fenster",
     "Doppeltür") shared across many channels. Move + step/stop + status all in
     the SAME per-channel function. The step/stop GA is DPT 1.007 named only
     "Schritt/Stop" — no shutter keyword — so the name classifier leaves it
     category 'unknown'. It must still be recognised (its Function role is
     StopStepUpDown) and paired to its own move. (26 of 33 covers were dropped.)
  B. Actuator-level Function per physical unit ("Markise RoomA/B"), name carries
     the zone. Its zone token collides with a plain window from group A — the
     Function boundary must stop the window from stealing the awning's step/stop.
  C. Function-less collective ("Westseite Rollläden" vs "Westseite Markisen") —
     both share the zone token "Westseite" and differ only by the TYPE token, no
     ETS Function at all. Pure name territory: the type token must decide, so the
     roller move takes its own step/stop, not the awning's.

Before the fix: A → no move_short (category gate drops the 'unknown' step/stop);
C → roller cross-wires to the awning's step/stop (zone token alone matched).
"""
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.generate_ha import generate_ha_yaml


def _ga(addr, name, dmain, dsub):
    return {"name": name, "identifier": f"GA-{addr}", "raw_address": 0, "address": addr,
            "project_uid": None, "dpt": {"main": dmain, "sub": dsub}, "data_secure": False,
            "communication_object_ids": [], "description": "", "comment": ""}


def _fn(name, *addr_roles):
    return {"name": name,
            "group_addresses": {a: {"address": a, "role": r} for a, r in addr_roles}}


def _build():
    gas: dict = {}
    fns: dict = {}
    # A. per-channel functions, shared generic display name, shutter roles.
    for sub, zone, fname in [(26, "RoomA Fenster", "Fenster"),
                             (3, "RoomB Doppeltür", "Doppeltür")]:
        gas[f"2/1/{sub}"] = _ga(f"2/1/{sub}", f"{zone} Bewegen", 1, 8)
        gas[f"2/2/{sub}"] = _ga(f"2/2/{sub}", f"{zone} Schritt/Stop", 1, 7)  # bare 1.007
        gas[f"2/3/{sub}"] = _ga(f"2/3/{sub}", f"{zone} Status Position", 5, 1)
        fns[f"FN-{fname}-{sub}"] = _fn(fname, (f"2/1/{sub}", "MoveUpDown"),
                                       (f"2/2/{sub}", "StopStepUpDown"),
                                       (f"2/3/{sub}", "PositionStatus"))
    # B. actuator-level functions, name carries the (colliding) zone token.
    for sub, zone, fname in [(50, "RoomA Markise", "Markise RoomA"),
                             (52, "RoomB Markise", "Markise RoomB")]:
        gas[f"2/1/{sub}"] = _ga(f"2/1/{sub}", f"{zone} Bewegen", 1, 8)
        gas[f"2/2/{sub}"] = _ga(f"2/2/{sub}", f"{zone} Schritt/Stop", 1, 7)
        gas[f"2/3/{sub}"] = _ga(f"2/3/{sub}", f"{zone} Status Position", 5, 1)
        fns[f"FN-{fname}"] = _fn(fname, (f"2/1/{sub}", ""),
                                 (f"2/2/{sub}", ""), (f"2/3/{sub}", ""))
    # C. function-less collective: same zone, different type token.
    gas["2/5/10"] = _ga("2/5/10", "Westseite Rollläden auf/ab", 1, 8)
    gas["2/5/11"] = _ga("2/5/11", "Westseite Rollläden Start/Stopp", 1, 7)
    gas["2/5/15"] = _ga("2/5/15", "Westseite Markisen auf/ab", 1, 8)
    gas["2/5/16"] = _ga("2/5/16", "Westseite Markisen Start/Stopp", 1, 7)
    # D. a foreign bare 1.007 (a lighting relative-dim step) sharing only the zone
    # token must NOT be stolen as the roller's step/stop — the roller takes its own
    # real stop (audit finding on this fix; the bare-DPT admission needs a shutter
    # name signal, and "…Schritt" carries none).
    gas["2/6/0"] = _ga("2/6/0", "Nordseite Rollläden auf/ab", 1, 8)
    gas["2/6/1"] = _ga("2/6/1", "Nordseite Licht Schritt", 1, 7)      # foreign step
    gas["2/6/2"] = _ga("2/6/2", "Nordseite Rollläden Stopp", 1, 10)   # own stop

    raw = {"info": {"group_address_style": "ThreeLevel", "schema_version": "21"},
           "group_addresses": gas, "communication_objects": {}, "devices": {},
           "functions": fns, "topology": {},
           # Main-2 named in German that our keyword list does NOT map to shutter,
           # so a bare 1.007 "Schritt/Stop" stays 'unknown' — mirrors the field
           # project (the bug only shows when the range name doesn't rescue it).
           "group_ranges": {"2": {"address_start": 4096, "name": "Beschattung",
                                  "group_ranges": {}}}}
    return build_loaded_from_raw(raw, "cover-pairing.knxproj")


def _covers(res):
    import yaml as _yaml
    doc = _yaml.safe_load(res["yaml"])
    return (doc or {}).get("knx", {}).get("cover", []) or []


def main():
    project = _build()
    covers = {c["move_long_address"]: c for c in _covers(generate_ha_yaml(project))}

    # Every cover must pair to ITS OWN step/stop and position status.
    expected = {
        "2/1/26": ("2/2/26", "2/3/26"),   # A: own 1.007 (role-rescued), not dropped
        "2/1/3":  ("2/2/3",  "2/3/3"),    # A
        "2/1/50": ("2/2/50", "2/3/50"),   # B: own, function-isolated from the window
        "2/1/52": ("2/2/52", "2/3/52"),   # B
        "2/5/10": ("2/5/11", None),       # C: roller takes its own, NOT 2/5/16
        "2/5/15": ("2/5/16", None),       # C: awning keeps its own
        "2/6/0":  ("2/6/2",  None),       # D: own stop, NOT the foreign light step
    }
    # D: the foreign lighting step must never be borrowed as a cover control.
    assert "2/6/1" not in [c.get("move_short_address") for c in covers.values()], \
        "a foreign 1.007 (lighting step) was mis-paired as a cover step/stop"
    for mv, (step, spos) in expected.items():
        assert mv in covers, f"missing cover for {mv}: {sorted(covers)}"
        got = covers[mv].get("move_short_address")
        assert got == step, f"{mv}: move_short {got!r}, expected {step!r}"
        if spos is not None:
            gp = covers[mv].get("position_state_address")
            assert gp == spos, f"{mv}: position_state {gp!r}, expected {spos!r}"

    # No step/stop is used as move_short by more than one cover (no stealing).
    shorts = [c.get("move_short_address") for c in covers.values()
              if c.get("move_short_address")]
    assert len(shorts) == len(set(shorts)), f"a step/stop was shared: {shorts}"

    print("test_cover_pairing: OK — each cover pairs its own step/stop across "
          "per-channel functions (A), actuator functions with zone collision (B), "
          "and function-less type-token collectives (C); no cross-wiring, none dropped.")


if __name__ == "__main__":
    main()
