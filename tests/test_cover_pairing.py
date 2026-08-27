"""Regression: generate_ha_package must not cross-wire a cover's step/stop
(move_short) across ETS Function boundaries (issue #11, field report by Kris1166).

A room that holds both a window and an awning shares a zone token ("Room A"), so
name-token pairing alone grabbed the wrong shutter's Step/Stop — and, because the
correct one then looked "taken", a cleanly-named cover could end up with no
move_short at all. ETS Function membership is authoritative: a step/stop owned by
a DIFFERENT function is another shutter's GA and must never be borrowed.

Fixture mirrors the reporter's anonymised table exactly (main group 2 = shutters,
3-level; move=1.008 at 2/1/N, step/stop=1.007 at 2/2/N, status position=5.001 at
2/3/N), each window/awning/door grouped in its own ETS Function. The "West Side
Roller Shutters" collective move (2/5/10) has NO own function, its step/stop
(2/5/11) is unlinked, and "West Side Awnings" (2/5/15/16) is a function — so the
collective must fall back to its own 2/5/11 and never steal 2/5/16.
"""
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.generate_ha import generate_ha_yaml


def _ga(addr, name, dmain, dsub):
    return {"name": name, "identifier": f"GA-{addr}", "raw_address": 0, "address": addr,
            "project_uid": None, "dpt": {"main": dmain, "sub": dsub}, "data_secure": False,
            "communication_object_ids": [], "description": "", "comment": ""}


def _fn(name, *addrs):
    return {"name": name,
            "group_addresses": {a: {"address": a, "role": ""} for a in addrs}}


_SHUTTERS = {
    0:  "Room A Window 1",
    1:  "Room A Window 2",
    2:  "Room C Double Door",   # non-colliding control — must keep its own step/stop
    3:  "Room B Double Door",
    50: "Awning Balcony Room A",
    51: "Awning Balcony Room C",
    52: "Awning Balcony Room B",
}


def _build():
    gas: dict = {}
    functions: dict = {}
    # Insertion order matters: the cover builder scans GAs in project order and
    # first-match wins. We insert the AWNINGS' move commands BEFORE the windows' —
    # the ordering under which an awning, sharing the "Room A" zone token, grabs a
    # window's Step/Stop (the field-reported cross-wiring). Without the ETS-Function
    # boundary this steals across shutters; with it, each stays in its own function.
    for base in (50, 51, 52, 0, 1, 2, 3):          # awning moves first
        a = f"2/1/{base}"
        gas[a] = _ga(a, f"{_SHUTTERS[base]} Move", 1, 8)
    for base in (0, 1, 2, 3, 50, 51, 52):          # then all step/stops
        a = f"2/2/{base}"
        gas[a] = _ga(a, f"{_SHUTTERS[base]} Step/Stop", 1, 7)
    for base in (0, 1, 2, 3, 50, 51, 52):          # then all position statuses
        a = f"2/3/{base}"
        gas[a] = _ga(a, f"{_SHUTTERS[base]} Status Position", 5, 1)
    for base, name in _SHUTTERS.items():           # each shutter = its own ETS Function
        functions[name] = _fn(name, f"2/1/{base}", f"2/2/{base}", f"2/3/{base}")
    # West Side: collective roller-shutter move with NO own function; its own
    # step/stop unlinked; the awnings ARE a function.
    gas["2/5/10"] = _ga("2/5/10", "West Side Roller Shutters Move", 1, 8)
    gas["2/5/11"] = _ga("2/5/11", "West Side Roller Shutters Step/Stop", 1, 7)
    gas["2/5/15"] = _ga("2/5/15", "West Side Awnings Move", 1, 8)
    gas["2/5/16"] = _ga("2/5/16", "West Side Awnings Step/Stop", 1, 7)
    functions["West Side Awnings"] = _fn("West Side Awnings", "2/5/15", "2/5/16")

    raw = {"info": {"group_address_style": "ThreeLevel", "schema_version": "21"},
           "group_addresses": gas, "communication_objects": {}, "devices": {},
           "functions": functions, "topology": {},
           "group_ranges": {"2": {"address_start": 4096, "name": "Shutters/Blinds",
                                  "group_ranges": {}}}}
    return build_loaded_from_raw(raw, "cover-pairing.knxproj")


def main():
    project = _build()
    res = generate_ha_yaml(project)
    covers = {c["move_long_address"]: c for c in
              [e for e in _covers(res)]}

    # Each shutter must pair to ITS OWN step/stop and status, never a sibling's.
    expected = {
        "2/1/0":  ("2/2/0",  "2/3/0"),   # Room A Window 1  (NOT 2/2/50)
        "2/1/1":  ("2/2/1",  "2/3/1"),   # Room A Window 2  (NOT 2/2/51)
        "2/1/2":  ("2/2/2",  "2/3/2"),   # Room C Double Door — keeps its own
        "2/1/3":  ("2/2/3",  "2/3/3"),   # Room B Double Door (NOT 2/2/52)
        "2/1/50": ("2/2/50", "2/3/50"),  # Awning Balcony Room A
        "2/1/51": ("2/2/51", "2/3/51"),
        "2/1/52": ("2/2/52", "2/3/52"),
        "2/5/15": ("2/5/16", None),      # West Side Awnings (own function)
    }
    for mv, (step, spos) in expected.items():
        assert mv in covers, f"missing cover for {mv}: {sorted(covers)}"
        got = covers[mv].get("move_short_address")
        assert got == step, f"{mv}: move_short {got!r}, expected {step!r}"
        if spos is not None:
            gp = covers[mv].get("position_state_address")
            assert gp == spos, f"{mv}: position_state {gp!r}, expected {spos!r}"

    # The collective (no own function) must fall back to its own 2/5/11, not steal
    # the awnings' 2/5/16.
    assert "2/5/10" in covers, sorted(covers)
    assert covers["2/5/10"].get("move_short_address") == "2/5/11", \
        covers["2/5/10"]

    # And no step/stop is used as move_short by more than one cover (no stealing).
    shorts = [c.get("move_short_address") for c in covers.values()
              if c.get("move_short_address")]
    assert len(shorts) == len(set(shorts)), f"a step/stop was shared: {shorts}"

    print("test_cover_pairing: OK — step/stop and status pair within the ETS "
          "Function; no cross-wiring across window/awning sharing a zone token.")


def _covers(res):
    """Extract the cover list from the generated package (yaml text or counts)."""
    import yaml as _yaml
    doc = _yaml.safe_load(res["yaml"])
    return (doc or {}).get("knx", {}).get("cover", []) or []


if __name__ == "__main__":
    main()
