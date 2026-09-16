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
    ("1/0/1", "1.05 Bedroom - Ceiling - on/off", 1, 1),
    ("1/1/1", "1.05 Bedroom - Ceiling - on/off status", 1, 11),
    ("5/0/1", "Garden pump - on/off", 1, 1),
])
knxB = yaml.safe_load(generate_ha_yaml(pB)["yaml"].split("\n\n", 1)[1])["knx"]
lightsB = {l["address"]: l for l in knxB.get("light", [])}
assert "1/0/1" in lightsB and lightsB["1/0/1"].get("state_address") == "1/1/1", knxB
assert not any(s["address"] == "1/0/1" for s in knxB.get("switch", [])), knxB
print("OK: B — on/off lighting is a light with address + state_address, not a switch")

print("\nALL REAL-HOUSE REGRESSION TESTS PASSED")
