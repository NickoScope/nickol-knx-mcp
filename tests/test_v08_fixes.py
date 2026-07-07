"""v0.8 fixes, synthetic and self-contained (issues #3-#6).

1. positional command/status pairing (parallel middles, identical names)
2. self-reporting commands (actuator R+T object on the command GA)
3. main_group_unnamed reads authoritative GroupRange names
4. completeness grader counts pattern-named ranges
5. app-program parser: ComObjectRef merge + newest-version pick
"""
import sys, os, zipfile, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.analyze import detect_missing_status, validate_naming
from nickol_knx_mcp.advanced import completeness_grade
from nickol_knx_mcp.appprog_parser import parse_project


def ga(addr, name, main, sub, co_ids=None):
    return {
        "name": name, "identifier": f"GA-{addr}", "raw_address": 0,
        "address": addr, "project_uid": None,
        "dpt": ({"main": main, "sub": sub} if main is not None else None),
        "data_secure": False, "communication_object_ids": co_ids or [],
        "description": "", "comment": "",
    }


def make(gas, cos=None, ranges=None):
    raw = {
        "info": {"project_id": "P-T", "name": "SynthV08", "last_modified": "",
                 "group_address_style": "ThreeLevel", "guid": "x", "created_by": "t",
                 "schema_version": "21", "tool_version": "t", "xknxproject_version": "t",
                 "language_code": "ru-RU"},
        "communication_objects": cos or {},
        "devices": {}, "topology": {},
        "group_addresses": {g["address"]: g for g in gas},
        "group_ranges": ranges or {},
        "functions": {},
    }
    return build_loaded_from_raw(raw, "synthetic-v08")


# 1) POSITIONAL PAIRING: command 1/0/7 and status 1/1/7 share the exact name —
#    no lexical marker anywhere; must NOT be flagged. An unpaired command must stay flagged.
proj = make([
    ga("1/0/7", "Light-Кухня-Люстра-onoff", 1, 1),
    ga("1/1/7", "Light-Кухня-Люстра-onoff", 1, 1),    # parallel middle, same sub, plain 1.001 — invisible to the lexical matcher
    ga("2/0/9", "Штора Кабинет вверх/вниз", 1, 8),     # no pair anywhere -> warning
])
f = detect_missing_status(proj)
warn = [x for x in f if x["code"] == "missing_status_address"]
assert len(warn) == 1 and warn[0]["address"] == "2/0/9", warn
summary = [x for x in f if x["code"] == "status_pairing_summary"]
# both directions count (the parallel-middle twin is itself command-classified),
# which is fine: neither GA lacks feedback
assert summary and "2 command(s) paired positionally" in summary[0]["message"], summary

# 2) SELF-REPORTING: the actuator's R+T object sits on the command GA itself.
cos = {
    "CO-W": {"name": "cmd", "number": 1, "flags": {"read": False, "write": True,
             "communication": True, "transmit": False, "update": False},
             "dpts": [{"main": 1, "sub": 1}], "group_address_links": ["1/0/1"]},
    "CO-RT": {"name": "state", "number": 2, "flags": {"read": True, "write": False,
              "communication": True, "transmit": True, "update": False},
              "dpts": [{"main": 1, "sub": 1}], "group_address_links": ["1/0/1"]},
}
proj = make([ga("1/0/1", "Розетка Кабинет", 1, 1, co_ids=["CO-W", "CO-RT"])], cos=cos)
f = detect_missing_status(proj)
assert not [x for x in f if x["code"] == "missing_status_address"], f
assert any("self-reporting" in x["message"] for x in f if x["code"] == "status_pairing_summary")

# 3) MAIN NAMES from GroupRanges: main 1 IS named in ranges (GA-level main_name may
#    lie); main 2 truly unnamed -> exactly one finding, for main 2.
ranges = {
    "1": {"name": "Освещение", "group_ranges": {"1/0": {"name": "Команды"}}},
    "2": {"name": "", "group_ranges": {}},
}
proj = make([ga("1/0/1", "Свет Кухня статус", 1, 11), ga("2/0/1", "Штора Спальня вверх/вниз", 1, 8)],
            ranges=ranges)
un = [x for x in validate_naming(proj) if x["code"] == "main_group_unnamed"]
assert len(un) == 1 and un[0]["address"].startswith("2/"), un

# 4) GRADER counts pattern-named ranges: GA names are plain, the middle is called «Сцены».
ranges = {"1": {"name": "Свет", "group_ranges": {"1/5": {"name": "Сцены"}}}}
proj = make([ga("1/5/1", "Гостиная вечер", 18, 1)], ranges=ranges)
g = completeness_grade(proj)
assert g["patterns_present"].get("scenes"), g

# 5) PARSER v2: ref-level merge + version pick.
HW = """<?xml version="1.0" encoding="utf-8"?>
<KNX><ManufacturerData><Manufacturer RefId="M-0073"><Hardware>
<Hardware Id="M-0073_H-T-1" Name="RefVendor Dev" SerialNumber="RV-1">
<Products><Product Id="M-0073_H-T-1_P-1" OrderNumber="RV-1" /></Products>
<Hardware2Programs><Hardware2Program>
<ApplicationProgramRef RefId="M-0073_A-0001-12-AAAA" />
<ApplicationProgramRef RefId="M-0073_A-0001-10-BBBB" />
</Hardware2Program></Hardware2Programs>
</Hardware>
</Hardware></Manufacturer></ManufacturerData></KNX>"""
APP_V18 = """<?xml version="1.0" encoding="utf-8"?>
<KNX><ManufacturerData><Manufacturer><ApplicationPrograms>
<ApplicationProgram Id="M-0073_A-0001-12-AAAA" ApplicationVersion="18"><Static><ComObjectTable>
<ComObject Id="O-1" Name="Object 1" Number="1" ObjectSize="1 Bit" CommunicationFlag="Enabled" />
<ComObject Id="O-2" Name="Object 2" Number="2" ObjectSize="1 Byte" CommunicationFlag="Enabled" />
</ComObjectTable>
<ComObjectRefs>
<ComObjectRef Id="O-1_R-1" RefId="O-1" Text="Switch A" DatapointType="DPST-1-1" WriteFlag="Enabled" />
<ComObjectRef Id="O-2_R-1" RefId="O-2" Text="Value A" DatapointType="DPST-5-1" />
<ComObjectRef Id="O-2_R-2" RefId="O-2" Text="Value B" DatapointType="DPST-5-10" />
</ComObjectRefs>
</Static></ApplicationProgram>
</ApplicationPrograms></Manufacturer></ManufacturerData></KNX>"""
APP_V16 = APP_V18.replace("A-0001-12-AAAA", "A-0001-10-BBBB").replace(
    'ApplicationVersion="18"', 'ApplicationVersion="16"').replace("Switch A", "OLD Switch")

with tempfile.TemporaryDirectory() as d:
    arc = os.path.join(d, "refvendor.knxprod")
    with zipfile.ZipFile(arc, "w") as z:
        z.writestr("M-0073/Hardware.xml", HW)
        z.writestr("M-0073/M-0073_A-0001-12-AAAA.xml", APP_V18)
        z.writestr("M-0073/M-0073_A-0001-10-BBBB.xml", APP_V16)
    res = parse_project(arc)
    dev = res["devices"][0]
    # newest app (v18, hex 12) picked even though listed FIRST is fine — but the
    # stale one (hex 10) was listed LAST, which the old [-1] logic would pick.
    assert dev["application_program"]["app_id"].endswith("12-AAAA"), dev["application_program"]
    o1 = [o for o in dev["comm_objects"] if o["number"] == 1][0]
    assert o1["dpt"] == "1.001" and o1["name"] == "Switch A", o1        # merged from ref
    assert o1["flags"]["W"] is True, o1                                  # flag from ref
    o2 = [o for o in dev["comm_objects"] if o["number"] == 2][0]
    assert o2["dpt"] is None and "5.001" in o2.get("dpt_variants", ""), o2  # refs disagree -> honest

print("OK — v0.8: positional pairing, self-reporting, range names (naming+grader), ref-merge + version pick")
