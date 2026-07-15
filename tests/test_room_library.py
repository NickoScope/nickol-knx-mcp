"""Room Template Library — R1 tests.

Covers the plan's required cases:
  (a) golden RU/EN — one template gives a stable, exact result;
  (b) idempotency — same input -> byte-identical output;
  (c) permutation invariance — reordering rooms -> identical addresses;
  (d) address exhaustion — a clear error, never a silent overflow;
  (e) round-trip — generated house -> load_project -> 0 errors from our linters
      (validate_naming / detect_missing_status / detect_dpt_issues / check_policy);
  (f) negative-oracle — a hand-written expected function/GA manifest vs the fact.
"""
import hashlib
import tempfile
import os

from nickol_knx_mcp import room_library as rl
from nickol_knx_mcp.project import load_project
from nickol_knx_mcp.analyze import (validate_naming, detect_missing_status,
                                     detect_dpt_issues)
from nickol_knx_mcp.policy import check_policy, load_policy


# --------------------------------------------------------------------------- #
# Golden: a single bedroom (comfort) — exact address -> (name, dpt) in RU and EN.
# Hand-verified structure: 26 GAs = dimmer(5) + 2×switch(2) + 2×shutter(4)
# + climate(7) + presence(2).
# --------------------------------------------------------------------------- #
GOLDEN_BEDROOM_RU = {
    "1/0/1": ("Спальня основной свет вкл/выкл", "1.001"),
    "1/0/2": ("Спальня прикроватный свет 1 вкл/выкл", "1.001"),
    "1/0/3": ("Спальня прикроватный свет 2 вкл/выкл", "1.001"),
    "1/1/1": ("Спальня основной свет диммирование", "3.007"),
    "1/2/1": ("Спальня основной свет яркость", "5.001"),
    "1/3/1": ("Спальня основной свет статус", "1.011"),
    "1/3/2": ("Спальня прикроватный свет 1 статус", "1.011"),
    "1/3/3": ("Спальня прикроватный свет 2 статус", "1.011"),
    "1/4/1": ("Спальня основной свет яркость статус", "5.001"),
    "2/0/1": ("Спальня окно 1 вверх/вниз", "1.008"),
    "2/0/2": ("Спальня окно 2 вверх/вниз", "1.008"),
    "2/1/1": ("Спальня окно 1 стоп", "1.010"),
    "2/1/2": ("Спальня окно 2 стоп", "1.010"),
    "2/2/1": ("Спальня окно 1 позиция", "5.001"),
    "2/2/2": ("Спальня окно 2 позиция", "5.001"),
    "2/4/1": ("Спальня окно 1 позиция статус", "5.001"),
    "2/4/2": ("Спальня окно 2 позиция статус", "5.001"),
    "3/0/1": ("Спальня тёплый пол вкл/выкл", "1.001"),
    "3/1/1": ("Спальня тёплый пол режим", "20.102"),
    "3/2/1": ("Спальня тёплый пол уставка", "9.001"),
    "3/4/1": ("Спальня тёплый пол статус", "1.011"),
    "3/4/2": ("Спальня тёплый пол уставка статус", "9.001"),
    "3/4/3": ("Спальня тёплый пол режим статус", "20.102"),
    "3/5/1": ("Спальня тёплый пол температура факт", "9.001"),
    "4/0/1": ("Спальня датчик присутствие", "1.018"),
    "4/1/1": ("Спальня датчик освещённость", "9.004"),
}
GOLDEN_BEDROOM_EN = {
    "1/0/1": ("Bedroom main light on/off", "1.001"),
    "1/0/2": ("Bedroom bedside light 1 on/off", "1.001"),
    "1/0/3": ("Bedroom bedside light 2 on/off", "1.001"),
    "1/1/1": ("Bedroom main light dimming", "3.007"),
    "1/2/1": ("Bedroom main light brightness", "5.001"),
    "1/3/1": ("Bedroom main light status", "1.011"),
    "1/3/2": ("Bedroom bedside light 1 status", "1.011"),
    "1/3/3": ("Bedroom bedside light 2 status", "1.011"),
    "1/4/1": ("Bedroom main light brightness status", "5.001"),
    "2/0/1": ("Bedroom window 1 up/down", "1.008"),
    "2/0/2": ("Bedroom window 2 up/down", "1.008"),
    "2/1/1": ("Bedroom window 1 stop", "1.010"),
    "2/1/2": ("Bedroom window 2 stop", "1.010"),
    "2/2/1": ("Bedroom window 1 position", "5.001"),
    "2/2/2": ("Bedroom window 2 position", "5.001"),
    "2/4/1": ("Bedroom window 1 position status", "5.001"),
    "2/4/2": ("Bedroom window 2 position status", "5.001"),
    "3/0/1": ("Bedroom floor heating on/off", "1.001"),
    "3/1/1": ("Bedroom floor heating mode", "20.102"),
    "3/2/1": ("Bedroom floor heating setpoint", "9.001"),
    "3/4/1": ("Bedroom floor heating status", "1.011"),
    "3/4/2": ("Bedroom floor heating setpoint status", "9.001"),
    "3/4/3": ("Bedroom floor heating mode status", "20.102"),
    "3/5/1": ("Bedroom floor heating actual temperature", "9.001"),
    "4/0/1": ("Bedroom sensor occupancy", "1.018"),
    "4/1/1": ("Bedroom sensor illuminance", "9.004"),
}


def _obj_map(house):
    return {o.address: (o.name, f"{o.dpt_main}.{o.dpt_sub:03d}") for o in house.objects}


def test_templates_all_valid():
    tmpls = rl.load_builtin_templates()
    assert set(tmpls) == {"bedroom", "children", "living", "kitchen",
                          "bathroom", "corridor"}, sorted(tmpls)
    for tid, t in tmpls.items():
        v = rl.validate_room_template(t)
        assert v["ok"], (tid, v["findings"])


def test_golden_ru_en():
    tmpls = rl.load_builtin_templates()
    room = [{"template": "bedroom", "preset": "comfort"}]
    hru = rl.resolve_house(room, tmpls, language="ru")
    hen = rl.resolve_house(room, tmpls, language="en")
    assert _obj_map(hru) == GOLDEN_BEDROOM_RU
    assert _obj_map(hen) == GOLDEN_BEDROOM_EN
    # identity is language-neutral: same addresses/DPTs regardless of labels
    assert set(_obj_map(hru)) == set(_obj_map(hen))
    assert {a: d for a, (_, d) in _obj_map(hru).items()} == \
           {a: d for a, (_, d) in _obj_map(hen).items()}


def test_idempotent():
    rooms = [{"template": "living", "preset": "comfort"},
             {"template": "bedroom", "preset": "comfort"},
             {"template": "kitchen", "preset": "basic"}]
    a = rl.compose(rooms, language="ru")["ets_xml"]
    b = rl.compose(rooms, language="ru")["ets_xml"]
    assert hashlib.sha256(a.encode()).digest() == hashlib.sha256(b.encode()).digest()


def test_permutation_invariant():
    rooms = [{"template": "living", "preset": "comfort"},
             {"template": "bedroom", "preset": "comfort"},
             {"template": "kitchen", "preset": "basic"},
             {"template": "bedroom", "preset": "basic"}]
    a = rl.compose(rooms, language="ru")["ets_xml"]
    b = rl.compose(list(reversed(rooms)), language="ru")["ets_xml"]
    assert a == b, "reordering rooms must not change the generated project"


def test_exhaustion_is_a_clear_error():
    # 300 lighting circuits overflow the 255-sub range of middle 1/0 -> hard error.
    try:
        rl.compose([{"template": "corridor", "preset": "basic",
                     "params": {"lighting_circuits": 300}}])
    except rl.RoomLibraryError as e:
        assert "exhausted" in str(e).lower() and "1/0" in str(e), str(e)
    else:
        raise AssertionError("address exhaustion must raise, never silently overflow")


def test_round_trip_zero_linter_errors():
    """The composed house, re-read by the STANDARD loader, must pass all four
    linters with 0 errors and 0 warnings (only INFO is acceptable)."""
    rooms = [{"template": "living", "preset": "comfort"},
             {"template": "bedroom", "preset": "comfort"},
             {"template": "bedroom", "preset": "basic"},
             {"template": "children", "preset": "comfort"},
             {"template": "kitchen", "preset": "comfort"},
             {"template": "bathroom", "preset": "comfort"},
             {"template": "corridor", "preset": "basic"}]
    house = rl.resolve_house(rooms, rl.load_builtin_templates(), language="ru")
    data = rl.build_knxproj_bytes(house)
    tf = tempfile.NamedTemporaryFile(suffix=".knxproj", delete=False)
    try:
        tf.write(data)
        tf.close()
        proj = load_project(tf.name)
    finally:
        os.unlink(tf.name)

    assert len(proj.gas) == len(house.objects), (len(proj.gas), len(house.objects))
    findings = (validate_naming(proj) + detect_missing_status(proj)
                + detect_dpt_issues(proj)
                + check_policy(proj, load_policy(None))["findings"])
    errors = [f for f in findings if f.get("severity") == "error"]
    warnings = [f for f in findings if f.get("severity") == "warning"]
    assert not errors, [(f["code"], f["address"]) for f in errors]
    assert not warnings, [(f["code"], f["address"]) for f in warnings]


def test_negative_oracle_manifest():
    """Hand-written expected function/GA set for corridor@comfort vs the fact."""
    house = rl.resolve_house([{"template": "corridor", "preset": "comfort"}],
                             rl.load_builtin_templates(), language="ru")
    expected = {
        "1/0/1": ("Коридор свет вкл/выкл", "1.001", "command", "lighting"),
        "1/1/1": ("Коридор свет диммирование", "3.007", "command", "lighting"),
        "1/2/1": ("Коридор свет яркость", "5.001", "command", "lighting"),
        "1/3/1": ("Коридор свет статус", "1.011", "status", "lighting"),
        "1/4/1": ("Коридор свет яркость статус", "5.001", "status", "lighting"),
        "4/0/1": ("Коридор датчик присутствие", "1.018", "sensor", "sensor"),
        "4/1/1": ("Коридор датчик освещённость", "9.004", "sensor", "sensor"),
    }
    fact = {o.address: (o.name, f"{o.dpt_main}.{o.dpt_sub:03d}", o.kind, o.domain)
            for o in house.objects}
    assert fact == expected, fact

    # manifest totals must agree with the resolved object count
    man = rl.build_manifest(house)
    assert man["totals"]["group_addresses"] == len(house.objects) == 7
    assert man["totals"]["rooms"] == 1


def test_per_slot_preset_override():
    """A slot-level preset override mixes comfort climate with basic lighting."""
    tmpls = rl.load_builtin_templates()
    house = rl.resolve_house([{"template": "bedroom", "preset": "comfort",
                               "slot_presets": {"main_light": "basic"}}],
                             tmpls, language="en")
    names = {o.name for o in house.objects}
    # main light downgraded to a switch -> no dimming/brightness objects for it
    assert "Bedroom main light on/off" in names
    assert not any("main light dimming" in n for n in names)
    # but the comfort climate slot is still present
    assert any("floor heating" in n for n in names)


def test_validate_rejects_bad_template():
    bad = {"schema_version": 99, "slot_id": "Bad Name",
           "labels": {"ru": "x"}, "parameters": {}, "slots": []}
    v = rl.validate_room_template(bad)
    assert not v["ok"]
    codes = {f["code"] for f in v["findings"]}
    assert "schema_version_unsupported" in codes
    assert "slot_id_invalid" in codes
    assert "label_missing" in codes
    assert "slots_missing" in codes


def test_bom_proposal():
    house = rl.resolve_house([{"template": "living", "preset": "comfort"}],
                             rl.load_builtin_templates(), language="ru")
    bom = rl.build_bom_proposal(house)
    fns = {i["function"]: i for i in bom["items"]}
    assert "lighting_dimmer" in fns and fns["lighting_dimmer"]["channels_required"] >= 3
    assert "shutter" in fns and "climate_floor" in fns
    for item in bom["items"]:
        assert item["candidate_recipe"], item


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  {name}: OK")
    print("test_room_library: OK — golden RU/EN, idempotent, permutation-invariant, "
          "exhaustion-safe, round-trip 0 errors/0 warnings, negative-oracle verified.")


if __name__ == "__main__":
    main()
