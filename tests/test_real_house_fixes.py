"""Regressions found on a real 1312-GA Zennio house (ETS 5.7), anonymised.

A. subdpt_suspect false positives
   - a 1-bit flag named after a quantity ("on by motion detector by illuminance",
     "CO2 threshold 1") is a flag, not the value -> never checked;
   - date/time and text GAs are never checked ("meter value recorded, date");
   - legitimate DPTs for the same quantity are not "wrong": power 9.024 kW,
     power factor 14.057, reactive energy 13.015, power 14.056 under an
     "electricity" name. (Checked against xknx 3.20.)
   - real findings survive: a bare DPT 9 named "lux threshold", a 5.x named
     "temperature control".
B. on/off lighting (1.001, lighting category) is emitted as a Home Assistant light
   (address + state_address), not a switch. A brightness-only light, which HA would
   reject for lacking `address`, goes to review (tested in test_pipeline.py).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.analyze import detect_dpt_issues


def _ga(addr, name, main, sub):
    return {"name": name, "identifier": f"GA-{addr}", "raw_address": 0, "address": addr,
            "project_uid": None, "dpt": {"main": main, "sub": sub} if main else None,
            "data_secure": False, "communication_object_ids": [], "description": "", "comment": ""}


def _project(rows):
    return build_loaded_from_raw({"group_addresses": {a: _ga(a, n, m, s) for a, n, m, s in rows},
                                  "info": {"group_address_style": "ThreeLevel"}}, "mem")


# ---------------------------------------------------------------- A. subdpt_suspect
false_positives = [
    ("1/7/63", "1.04 - Winter garden - on by motion by освещенности", 1, 6),
    ("1/7/70", "1.01 - Vestibule вкл по ДД по освещенности", 1, 2),
    ("6/0/3", "Опорный сигнал освещенности для дневного откл ДД", 1, 1),
    ("2/5/1", "02. Living - порог CO2 1", 1, 1),
    ("5/2/1", "Электроэнергия - запись значения, дата", 11, 1),
    ("5/2/8", "3 Фазы - Активная мощность, кВт", 9, 24),
    ("5/2/9", "Boiler produced мощность", 9, 24),
    ("5/2/10", "3 Фазы - Фактор мощности", 14, 57),
    ("5/2/13", "3 Фазы - Индуктивная реактивная энергия", 13, 15),
    ("5/2/20", "Электроэнергия - Текущее потребление, W", 14, 56),
    ("5/2/21", "Meter energy MWh", 13, 16),
]
real_findings = [
    ("1/5/1", "01. Corridor PDK1.1 - порог освещенности, люкс", 9, None),
    ("3/1/1", "ПВУ 1 - Контроль температуры", 5, None),
    ("5/2/30", "Phase power L1", 5, 1),
    ("5/2/31", "Room temperature", 9, 2),
]
p = _project(false_positives + real_findings)
flagged = {f["address"] for f in detect_dpt_issues(p) if f["code"] == "subdpt_suspect"}
wrong = [a for a, *_ in false_positives if a in flagged]
assert not wrong, f"false positives still flagged: {wrong}"
missed = [a for a, *_ in real_findings if a not in flagged]
assert not missed, f"real findings no longer flagged: {missed}"
print(f"OK: A — {len(false_positives)} false positives silent, {len(real_findings)} real findings still flagged")

# ---------------------------------------------------------------- B. on/off lighting -> light
import yaml
from nickol_knx_mcp.generate_ha import generate_ha_yaml

pB = _project([
    ("1/0/1", "1.05 Bedroom - Ceiling light - on/off", 1, 1),
    ("1/1/1", "1.05 Bedroom - Ceiling light - on/off status", 1, 11),
    ("5/0/1", "Garden pump - on/off", 1, 1),
])
knxB = yaml.safe_load(generate_ha_yaml(pB)["yaml"].split("\n\n", 1)[1])["knx"]
lightsB = {l["address"]: l for l in knxB.get("light", [])}
assert "1/0/1" in lightsB and lightsB["1/0/1"].get("state_address") == "1/1/1", knxB
assert not any(s["address"] == "1/0/1" for s in knxB.get("switch", [])), knxB
print("OK: B — on/off lighting is a light with address + state_address, not a switch")

# ---------------------------------------------------------------- C. self-reporting status
def _proj_with_cos(rows, flags_by_addr):
    gas, cos = {}, {}
    for a, n, m, s in rows:
        g = _ga(a, n, m, s)
        if a in flags_by_addr:
            cid = f"CO-{a}"
            g["communication_object_ids"] = [cid]
            cos[cid] = {"flags": flags_by_addr[a], "group_address_links": [a], "dpts": [], "text": "", "function_text": ""}
        gas[a] = g
    return build_loaded_from_raw({"group_addresses": gas, "communication_objects": cos,
                                  "info": {"group_address_style": "ThreeLevel"}}, "mem")

pC = _proj_with_cos(
    [("1/0/5", "1.02 Hall - Ceiling light - on/off", 1, 1),
     ("1/0/6", "1.03 Living - Floor lamp light - on/off", 1, 1),
     ("5/0/5", "Workshop socket - on/off", 1, 1)],
    {"1/0/5": {"write": True, "read": True, "transmit": True},
     "1/0/6": {"write": True, "read": False, "transmit": False},
     "5/0/5": {"write": True, "read": True, "transmit": True}})
resC = generate_ha_yaml(pC)
knxC = yaml.safe_load(resC["yaml"].split("\n\n", 1)[1])["knx"]
ents = {e["address"]: e for plat in ("light", "switch") for e in knxC.get(plat, [])}
assert ents["1/0/5"].get("state_address") == "1/0/5", ents
assert ents["5/0/5"].get("state_address") == "5/0/5", ents
assert "state_address" not in ents["1/0/6"], ents
no_status = {r["address"] for r in resC["review"] if r["reason"] in ("light_without_status", "switch_without_status")}
assert no_status == {"1/0/6"}, no_status
print("OK: C — Read+Transmit object on the command GA is its own state; write-only stays in review")

# ---------------------------------------------------------------- E. climate: one entity per device
# A room with floor heating + convector + AC unit sharing one air sensor used to become ONE climate
# (convector setpoint, AC controller mode, AC fan speed as "valve"). Room codes lost their floor
# digit (1.09 matched 2.09 and a central GA), and "Kids room 1" matched "Kids room 2".
pE = _project([
    ("2/0/6", "1.05 Bedroom - Air temperature", 9, 1),
    ("2/2/20", "1.05 Bedroom - Convector - Уставка", 9, 1),
    ("2/2/21", "1.05 Bedroom - Convector - Уставка - Статус", 9, 1),
    ("2/2/22", "1.05 Bedroom - Convector - Режим", 20, 102),
    ("2/2/23", "1.05 Bedroom - Convector - Режим - Статус", 20, 102),
    ("2/5/37", "1.05 Bedroom -А/С - Уставка", 9, 1),
    ("2/5/38", "1.05 Bedroom -А/С - Уставка - Статус", 9, 1),
    ("2/5/39", "1.05 Bedroom -А/С - Режим", 20, 105),
    ("2/5/40", "1.05 Bedroom -А/С - Режим - Статус", 20, 105),
    ("2/5/42", "1.05 Bedroom -А/С - Вентилятор - Статус", 5, 1),
    ("2/4/10", "1.09 Bath - Теплый пол - Уставка", 9, 1),
    ("2/4/11", "1.09 Bath - Теплый пол - Уставка - Статус", 9, 1),
    ("2/4/12", "1.09 Bath - Теплый пол - Режим", 20, 102),
    ("2/4/13", "1.09 Bath - Теплый пол - Режим - Статус", 20, 102),
    ("2/1/9", "1.09 Bath - Теплый пол - Температура", 9, 1),
    ("2/4/14", "1.09 Bath - Теплый пол - клапан - Статус", 5, 1),
    ("0/1/7", "09. Bath 1st floor ТП + стена - Уставка", 9, 1),
    ("2/3/0", "2.09 Lounge - Теплый пол - Уставка", 9, 1),
    ("2/3/1", "2.09 Lounge - Теплый пол - Уставка - Статус", 9, 1),
    ("2/3/2", "2.09 Lounge - Теплый пол - Режим", 20, 102),
    ("2/1/19", "2.09 Lounge - Теплый пол - Температура", 9, 1),
    ("3/0/1", "Kids room 1 temperature", 9, 1),
    ("3/0/2", "Kids room 2 temperature", 9, 1),
    ("3/1/1", "Kids room 1 AC setpoint", 9, 1),
    ("3/1/2", "Kids room 1 AC setpoint status", 9, 1),
    ("3/1/3", "Kids room 1 AC mode", 20, 102),
])
climE = yaml.safe_load(generate_ha_yaml(pE)["yaml"].split("\n\n", 1)[1])["knx"]["climate"]
by_mode = {(e.get("operation_mode_address") or e.get("controller_mode_address")): e for e in climE}
conv, ac, bath, lounge, kids = by_mode["2/2/22"], by_mode["2/5/39"], by_mode["2/4/12"], by_mode["2/3/2"], by_mode["3/1/3"]
assert conv["target_temperature_state_address"] == "2/2/21" and conv["temperature_address"] == "2/0/6", conv
assert "controller_mode_address" not in conv and "command_value_state_address" not in conv, conv
assert ac["target_temperature_state_address"] == "2/5/38" and ac["temperature_address"] == "2/0/6", ac
assert "command_value_state_address" not in ac and "operation_mode_address" not in ac, ac
assert bath["target_temperature_address"] == "2/4/10" and bath["temperature_address"] == "2/1/9", bath
assert bath.get("command_value_state_address") == "2/4/14", bath
assert lounge["target_temperature_state_address"] == "2/3/1" and lounge["temperature_address"] == "2/1/19", lounge
assert kids["temperature_address"] == "3/0/1", kids
controls = [e[k] for e in climE for k in e if k.endswith("address") and k != "temperature_address"]
assert len(controls) == len(set(controls)), controls
assert "0/1/7" not in controls, controls
print(f"OK: E — {len(climE)} climates, one per device; room code, numbers and device type keep them apart")

# ---------------------------------------------------------------- F. climate: LLM-council failure catalog
def _climates(rows):
    res = generate_ha_yaml(_project(rows))
    doc = yaml.safe_load(res["yaml"].split("\n\n", 1)[1]) or {}
    return (doc.get("knx") or {}).get("climate", []), res["review"]

def _controls(clims):
    return [e[k] for e in clims for k in e if k.endswith("address") and k != "temperature_address"]

# F1. two devices of the same type, told apart by a word -> two climates, no cross-wiring
cl, rv = _climates([
    ("4/0/1", "3.01 Hall - Air temperature", 9, 1),
    ("4/1/1", "3.01 Hall - Convector north - Setpoint", 9, 1),
    ("4/1/2", "3.01 Hall - Convector north - Setpoint status", 9, 1),
    ("4/1/3", "3.01 Hall - Convector north - HVAC mode", 20, 102),
    ("4/2/1", "3.01 Hall - Convector south - Setpoint", 9, 1),
    ("4/2/2", "3.01 Hall - Convector south - Setpoint status", 9, 1),
    ("4/2/3", "3.01 Hall - Convector south - HVAC mode", 20, 102),
])
by = {e["operation_mode_address"]: e for e in cl}
assert by["4/1/3"]["target_temperature_state_address"] == "4/1/2", cl
assert by["4/2/3"]["target_temperature_state_address"] == "4/2/2", cl
assert by["4/1/3"]["temperature_address"] == by["4/2/3"]["temperature_address"] == "4/0/1", cl
print("OK: F1 — same-type devices told apart by a word, shared room sensor")

# F2. two devices we cannot tell apart ("AC_1"/"AC_2") -> never merged, never a silent pick
cl, rv = _climates([
    ("5/0/1", "Hall temperature", 9, 1),
    ("5/1/1", "Hall AC_1 setpoint", 9, 1), ("5/1/2", "Hall AC_1 setpoint status", 9, 1),
    ("5/1/3", "Hall AC_1 mode", 20, 105),
    ("5/2/1", "Hall AC_2 setpoint", 9, 1), ("5/2/2", "Hall AC_2 setpoint status", 9, 1),
    ("5/2/3", "Hall AC_2 mode", 20, 105),
])
assert not cl, cl
assert {r["address"] for r in rv if r["reason"] in ("climate_ambiguous", "climate_duplicate_anchor")} == {"5/1/3", "5/2/3"}, rv
print("OK: F2 — indistinguishable same-type devices go to review, nothing is guessed")

# F3. a value or a device tag is not a room code or a room number; a shared room sensor
#     fits a numbered device ("Room 1 Temperature" for "Room 1 Floor heating 2")
cl, rv = _climates([
    ("6/0/1", "Room 1 Temperature", 9, 1),
    ("6/1/1", "Room 1 Floor heating 2 setpoint 21.5 °C", 9, 1),
    ("6/1/2", "Room 1 Floor heating 2 setpoint 21.5 °C status", 9, 1),
    ("6/1/3", "Room 1 Floor heating 2 D.1.2 HVAC mode", 20, 102),
])
assert len(cl) == 1 and cl[0]["temperature_address"] == "6/0/1" and cl[0]["target_temperature_state_address"] == "6/1/2", (cl, rv)
print("OK: F3 — '21.5' is no room code, 'D.1.2' no room number, shared sensor fits a numbered loop")

# F4. a second floor loop's word ("shower") keeps its members away from the main loop
cl, rv = _climates([
    ("7/0/1", "1.09 Bath - Air temperature", 9, 1),
    ("7/1/1", "1.09 Bath - Теплый пол - Уставка", 9, 1), ("7/1/2", "1.09 Bath - Теплый пол - Уставка - Статус", 9, 1),
    ("7/1/3", "1.09 Bath - Теплый пол - Режим", 20, 102),
    ("7/2/1", "1.09 Bath - Теплый пол душ - Уставка", 9, 1), ("7/2/2", "1.09 Bath - Теплый пол душ - Уставка - Статус", 9, 1),
    ("7/2/3", "1.09 Bath - Теплый пол душ - Режим", 20, 102),
])
by = {e["operation_mode_address"]: e for e in cl}
assert by["7/1/3"]["target_temperature_state_address"] == "7/1/2", cl
assert by["7/2/3"]["target_temperature_state_address"] == "7/2/2", cl
assert len(_controls(cl)) == len(set(_controls(cl))), cl
print("OK: F4 — main floor loop and shower loop each keep their own setpoint and mode")

# F5. only 20.102 / 20.105 anchor a climate
cl, rv = _climates([
    ("8/0/1", "Lab temperature", 9, 1), ("8/0/2", "Lab heating setpoint status", 9, 1),
    ("8/0/3", "Lab HVAC control mode", 20, 1),
])
assert not cl, cl
assert any(r["address"] == "8/0/3" for r in rv), rv   # not an anchor, but never dropped silently
print("OK: F5 — a 20.001 GA does not start a climate entity and still reaches review")

print("\nALL REAL-HOUSE REGRESSION TESTS PASSED")
