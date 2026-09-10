"""Structure-first entity suggestions (prototype of a 2nd HA KNX SuggestionProvider).

The fixture deliberately mirrors the HA FB-provider test project (core PR #180891):
group addresses are named "GA x/y/z" — NO semantics in names — and there are NO
functional blocks. A structure-first provider must still produce the same configs
the FB provider produces from DPAs, purely from device channels + object flags + DPTs.
"""
from nickol_knx_mcp.suggest import suggest_entities, FB_COVERED

SW, PCT, CT, RGB, UPD, STEP, STOP, TEMP, MODE = ({"main": 1, "sub": 1}, {"main": 5, "sub": 1},
    {"main": 7, "sub": 600}, {"main": 232, "sub": 600}, {"main": 1, "sub": 8},
    {"main": 1, "sub": 7}, {"main": 1, "sub": 10}, {"main": 9, "sub": 1}, {"main": 20, "sub": 102})


def _ga(a, dpt, name=None):
    return {"name": name or f"GA {a}", "address": a, "description": "", "dpt": dpt}


def _co(dev, links, *, write=False, transmit=False, read=False, dpts=None, channel=None):
    return {"name": "", "number": 0, "text": "", "function_text": "", "description": "",
            "device_address": dev, "device_application": None, "module_def": None,
            "channel": channel, "dpts": dpts or [], "object_size": "",
            "flags": {"read": read, "write": write, "communication": True, "transmit": transmit,
                      "update": False, "read_on_init": False},
            "group_address_links": links, "dpas": None}


def _ch(name, cos, fbs=None):
    return {"identifier": name, "name": name, "communication_object_ids": cos, "functional_blocks": fbs}


def _dev(addr, name, channels):
    return {"name": name, "hardware_name": "", "order_number": "", "description": "",
            "manufacturer_name": "", "individual_address": addr, "application": None,
            "project_uid": None, "communication_object_ids": [], "channels": channels}


def _project():
    gas = {a: _ga(a, d) for a, d in [
        ("1/0/1", SW), ("1/0/2", SW), ("1/0/3", SW), ("1/0/4", SW),
        ("2/0/1", UPD), ("2/0/2", STEP), ("2/0/3", PCT), ("2/0/4", PCT), ("2/0/5", PCT), ("2/0/6", PCT),
        ("5/0/1", SW), ("5/0/2", SW), ("5/0/3", PCT), ("5/0/4", PCT), ("5/0/5", CT), ("5/0/6", CT),
        ("6/0/1", SW), ("6/0/2", SW), ("6/0/3", RGB), ("6/0/4", RGB),
        ("3/0/1", TEMP), ("3/0/2", TEMP), ("3/0/3", TEMP), ("3/0/4", MODE), ("3/0/5", MODE),
        ("4/0/1", TEMP), ("4/0/2", SW), ("7/0/1", SW),
    ]}
    gas["8/0/1"] = _ga("8/0/1", SW, "Kitchen socket switch")
    gas["8/0/2"] = _ga("8/0/2", SW, "Kitchen socket switch status")
    cos = {
        # switch actuator channel: write 1/0/1 (+passive 1/0/2), status 1/0/3
        "co-1": _co("1.1.1", ["1/0/1", "1/0/2"], write=True, channel="CH-1"),
        "co-2": _co("1.1.1", ["1/0/3"], transmit=True, read=True, channel="CH-1"),
        "co-3": _co("1.1.1", ["1/0/4"], write=True, channel="CH-2"),
        # push button transmitting to 1/0/4 — a command, NOT a sensor
        "co-pb": _co("1.5.1", ["1/0/4"], transmit=True, channel="PB-1"),
        # cover: up/down, step, position set/state, slat set/state (by ORDER, no names)
        "co-10": _co("1.1.2", ["2/0/1"], write=True, channel="CH-1"),
        "co-11": _co("1.1.2", ["2/0/2"], write=True, channel="CH-1"),
        "co-12": _co("1.1.2", ["2/0/3"], write=True, channel="CH-1"),
        "co-13": _co("1.1.2", ["2/0/4"], transmit=True, channel="CH-1"),
        "co-14": _co("1.1.2", ["2/0/5"], write=True, channel="CH-1"),
        "co-15": _co("1.1.2", ["2/0/6"], transmit=True, channel="CH-1"),
        # tunable white
        "co-50": _co("1.2.1", ["5/0/1"], write=True, channel="CH-1"),
        "co-51": _co("1.2.1", ["5/0/2"], transmit=True, channel="CH-1"),
        "co-52": _co("1.2.1", ["5/0/3"], write=True, channel="CH-1"),
        "co-53": _co("1.2.1", ["5/0/4"], transmit=True, channel="CH-1"),
        "co-54": _co("1.2.1", ["5/0/5"], write=True, channel="CH-1"),
        "co-55": _co("1.2.1", ["5/0/6"], transmit=True, channel="CH-1"),
        # RGB
        "co-60": _co("1.2.2", ["6/0/1"], write=True, channel="CH-1"),
        "co-61": _co("1.2.2", ["6/0/2"], transmit=True, channel="CH-1"),
        "co-62": _co("1.2.2", ["6/0/3"], write=True, channel="CH-1"),
        "co-63": _co("1.2.2", ["6/0/4"], transmit=True, channel="CH-1"),
        # climate: current temp (source), target (sink) + target state, mode
        "co-70": _co("1.3.1", ["3/0/1"], transmit=True, read=True, channel="CH-1"),
        "co-71": _co("1.3.1", ["3/0/2"], write=True, channel="CH-1"),
        "co-72": _co("1.3.1", ["3/0/3"], transmit=True, channel="CH-1"),
        "co-73": _co("1.3.1", ["3/0/4"], write=True, channel="CH-1"),
        "co-74": _co("1.3.1", ["3/0/5"], transmit=True, channel="CH-1"),
        # pure sensors: a temperature and a contact nobody writes to
        "co-80": _co("1.4.1", ["4/0/1"], transmit=True, read=True, channel="S-1"),
        "co-81": _co("1.4.1", ["4/0/2"], transmit=True, channel="S-1"),
        # FB-covered channel: must be skipped (the FB provider owns it)
        "co-90": _co("1.6.1", ["7/0/1"], write=True, channel="CH-1"),
        # device WITHOUT channels, named GAs → fallback (name pairing)
        "co-95": _co("1.7.1", ["8/0/1"], write=True),
        "co-96": _co("1.7.1", ["8/0/2"], transmit=True),
    }
    devs = {
        "1.1.1": _dev("1.1.1", "Schaltaktor", {"CH-1": _ch("Ausgang 1", ["co-1", "co-2"]),
                                                "CH-2": _ch("Ausgang 2", ["co-3"])}),
        "1.5.1": _dev("1.5.1", "Taster", {"PB-1": _ch("Wippe 1", ["co-pb"])}),
        "1.1.2": _dev("1.1.2", "Jalousieaktor", {"CH-1": _ch("Jalousie 1", ["co-10", "co-11", "co-12", "co-13", "co-14", "co-15"])}),
        "1.2.1": _dev("1.2.1", "TW Aktor", {"CH-1": _ch("Tunable White", ["co-50", "co-51", "co-52", "co-53", "co-54", "co-55"])}),
        "1.2.2": _dev("1.2.2", "RGB Aktor", {"CH-1": _ch("RGB", ["co-60", "co-61", "co-62", "co-63"])}),
        "1.3.1": _dev("1.3.1", "Raumtemperaturregler", {"CH-1": _ch("RTR", ["co-70", "co-71", "co-72", "co-73", "co-74"])}),
        "1.4.1": _dev("1.4.1", "Sensor", {"S-1": _ch("Messwerte", ["co-80", "co-81"])}),
        "1.6.1": _dev("1.6.1", "Modern Aktor", {"CH-1": _ch("Ausgang FB", ["co-90"], fbs=["417"])}),
        "1.7.1": _dev("1.7.1", "Old Aktor", {}),
    }
    return {"info": {"name": "suggest-test", "group_address_style": "ThreeLevel", "schema_version": "21",
                     "xknxproject_version": "3.9.0"},
            "group_addresses": gas, "devices": devs, "communication_objects": cos,
            "functions": {}, "topology": {}, "group_ranges": {}}


def main():
    res = suggest_entities(_project())
    by = {s["id"]: s for s in res["suggestions"]}
    h = res["hints"]
    assert h["state"] == "ok" and h["skipped_fb_covered"] == 1, h

    # 1. switch actuator channel: same config the FB provider derives from DPAs
    s = by["1.1.1_CH-1"]
    assert s["platform_options"] == ["light", "switch"], s["platform_options"]
    assert s["suggestions"]["light"]["knx"] == {"ga_switch": {"write": "1/0/1", "state": "1/0/3", "passive": ["1/0/2"]}}
    assert s["suggestions"]["switch"]["knx"] == {"ga_switch": {"write": "1/0/1", "state": "1/0/3", "passive": ["1/0/2"]}}
    assert s["group_id"] == "1.1.1" and s["group_name"] == "Schaltaktor" and s["secondary_info"] == "Ausgang 1"
    assert s["metadata"]["tier"] == "structural" and s["metadata"]["review"], "plain 1.001 must ask light-or-switch"
    assert [m["address"] for m in s["suggestions"]["light"]["matched_group_addresses"]] == ["1/0/1", "1/0/2", "1/0/3"]

    # 2. the push button transmitting to 1/0/4 is NOT a binary_sensor (GA has a sink)
    assert not any(s2["id"].startswith("1.5.1_") for s2 in res["suggestions"]), "push button became a sensor"

    # 3. cover from order alone — identical to the FB expectation
    c = by["1.1.2_CH-1"]
    assert c["platform_options"] == ["cover"]
    assert c["suggestions"]["cover"]["knx"] == {
        "ga_up_down": {"write": "2/0/1"}, "ga_step": {"write": "2/0/2"},
        "ga_position_set": {"write": "2/0/3"}, "ga_position_state": {"state": "2/0/4"},
        "ga_angle": {"write": "2/0/5", "state": "2/0/6"}}, c["suggestions"]["cover"]["knx"]
    assert any("slat" in r for r in c["metadata"]["review"]), "angle-by-order must be flagged for review"

    # 4. tunable white with dpt derived from the GA
    t = by["1.2.1_CH-1"]
    assert t["platform_options"] == ["light"]
    assert t["suggestions"]["light"]["knx"] == {
        "ga_switch": {"write": "5/0/1", "state": "5/0/2"},
        "ga_brightness": {"write": "5/0/3", "state": "5/0/4"},
        "ga_color_temp": {"write": "5/0/5", "state": "5/0/6", "dpt": "7.600"}}, t["suggestions"]["light"]["knx"]

    # 5. RGB combined colour
    r = by["1.2.2_CH-1"]
    assert r["suggestions"]["light"]["knx"] == {
        "ga_switch": {"write": "6/0/1", "state": "6/0/2"},
        "color": {"ga_color": {"write": "6/0/3", "state": "6/0/4", "dpt": "232.600"}}}, r["suggestions"]["light"]["knx"]

    # 6. climate
    k = by["1.3.1_CH-1"]
    assert k["platform_options"] == ["climate"]
    assert k["suggestions"]["climate"]["knx"] == {
        "ga_temperature_current": {"state": "3/0/1"},
        "target_temperature": {"ga_temperature_target": {"write": "3/0/2", "state": "3/0/3"}},
        "ga_operation_mode": {"write": "3/0/4", "state": "3/0/5"}}, k["suggestions"]["climate"]["knx"]

    # 7. transmit-only GAs nobody writes to → sensor (with dpt) and binary_sensor
    assert by["1.4.1_S-1_4/0/1"]["suggestions"]["sensor"]["knx"] == {"ga_sensor": {"state": "4/0/1", "dpt": "9.001"}}
    assert by["1.4.1_S-1_4/0/2"]["suggestions"]["binary_sensor"]["knx"] == {"ga_sensor": {"state": "4/0/2"}}

    # 8. FB-covered channel skipped entirely
    assert "1.6.1_CH-1" not in by and not any("7/0/1" in str(s2["suggestions"]) for s2 in res["suggestions"])

    # 9. device WITHOUT channels: objects grouped into a pseudo-channel by vendor text
    #    (here empty → one group), state paired by flags; "socket" in the GA name → switch first
    f = next(s2 for s2 in res["suggestions"]
             if any(m["address"] == "8/0/1" for p in s2["suggestions"].values() for m in p["matched_group_addresses"]))
    assert f["group_id"] == "1.7.1", f["group_id"]
    assert f["platform_options"][0] == "switch", f["platform_options"]
    assert f["suggestions"]["switch"]["knx"]["ga_switch"] == {"write": "8/0/1", "state": "8/0/2"}
    assert h["pseudo_channels"] == 1 and h["fallback"] == 0, h

    # 10. no GA appears in two suggestions
    seen = {}
    for s2 in res["suggestions"]:
        for p, ps in s2["suggestions"].items():
            for m in ps["matched_group_addresses"]:
                assert seen.setdefault(m["address"], s2["id"]) == s2["id"], f"{m['address']} in two suggestions"
    print(f"test_suggest: OK — {len(res['suggestions'])} suggestions from structure alone on a nameless "
          f"fixture (FB-provider parity for switch/cover/TW/RGB), climate, sensors, FB-skip, name fallback; hints={h}")


if __name__ == "__main__":
    main()
