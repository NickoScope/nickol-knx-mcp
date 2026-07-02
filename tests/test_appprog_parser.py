"""appprog_parser: extract exact device object models from a (synthetic) .knxprod.

Self-contained: builds a minimal ETS-shaped archive in memory — no real project needed.
"""
import sys, os, io, zipfile, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nickol_knx_mcp.appprog_parser import parse_project, to_catalog_yaml, summary
import nickol_knx_mcp.device_library as dl

HARDWARE = """<?xml version="1.0" encoding="utf-8"?>
<KNX><ManufacturerData><Manufacturer RefId="M-0071"><Hardware>
<Hardware Id="M-0071_H-TST-1" Name="Test Dimmer 2CH" SerialNumber="TST-DIM2">
<Products><Product Id="M-0071_H-TST-1_P-1" OrderNumber="TST-DIM2" /></Products>
<Hardware2Programs><Hardware2Program>
<ApplicationProgramRef RefId="M-0071_A-TEST-1-0" />
</Hardware2Program></Hardware2Programs>
</Hardware>
</Hardware></Manufacturer></ManufacturerData></KNX>"""

APPPROG = """<?xml version="1.0" encoding="utf-8"?>
<KNX><ManufacturerData><Manufacturer><ApplicationPrograms>
<ApplicationProgram Id="M-0071_A-TEST-1-0" ApplicationVersion="7"><Static><ComObjectTable>
<ComObject Id="O-1" Name="oX.ch[0].onOff" Text="[C1] On/Off" Number="1" FunctionText="on/off" ObjectSize="1 Bit" ReadFlag="Disabled" WriteFlag="Enabled" CommunicationFlag="Enabled" TransmitFlag="Disabled" UpdateFlag="Disabled" DatapointType="DPST-1-1" />
<ComObject Id="O-2" Name="oX.ch[0].dim" Text="[C1] Relative Dimming" Number="2" ObjectSize="4 Bit" WriteFlag="Enabled" CommunicationFlag="Enabled" DatapointType="DPST-3-7" />
<ComObject Id="O-3" Name="oX.ch[1].onOff" Text="[C2] On/Off" Number="3" ObjectSize="1 Bit" WriteFlag="Enabled" CommunicationFlag="Enabled" DatapointType="DPST-1-1" />
<ComObject Id="O-4" Name="oX.ch[1].dim" Text="[C2] Relative Dimming" Number="4" ObjectSize="4 Bit" WriteFlag="Enabled" CommunicationFlag="Enabled" DatapointType="DPST-3-7" />
<ComObject Id="O-5" Name="oX.pattern" Text="[LF] Pattern" Number="5" ObjectSize="1 Byte" WriteFlag="Enabled" CommunicationFlag="Enabled" />
</ComObjectTable></Static></ApplicationProgram>
</ApplicationPrograms></Manufacturer></ManufacturerData></KNX>"""


def _make_archive(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("P-1/0.xml", "<KNX/>")  # a 'client project' the parser must NOT read
        z.writestr("M-0071/Hardware.xml", HARDWARE)
        z.writestr("M-0071/M-0071_A-TEST-1-0.xml", APPPROG)


with tempfile.TemporaryDirectory() as d:
    arc = os.path.join(d, "sample.knxprod")
    _make_archive(arc)

    res = parse_project(arc)
    cov = res["coverage"]
    assert cov["devices_parsed"] == 1, cov
    assert cov["objects_total"] == 5, cov
    assert cov["objects_without_dpt"] == 1, cov          # the [LF] Pattern, no DPT

    dev = res["devices"][0]
    assert dev["order_number"] == "TST-DIM2", dev
    assert dev["application_program"]["version"] == "v7", dev
    assert dev["object_counts"]["master_catalog_total"] == 5

    # DPT conversion DPST-x-y -> x.00y
    o2 = [o for o in dev["comm_objects"] if o["number"] == 2][0]
    assert o2["dpt"] == "3.007", o2
    o1 = [o for o in dev["comm_objects"] if o["number"] == 1][0]
    assert o1["dpt"] == "1.001" and o1["role"] == "cmd", o1
    o5 = [o for o in dev["comm_objects"] if o["number"] == 5][0]
    assert o5["dpt"] is None, "missing DatapointType must stay None, never guessed"

    # per-channel block detection: [C1]/[C2] -> 2 instances of 2 objects, stride 2
    blk = [b for b in dev["blocks"] if b["unit"] == "C"][0]
    assert blk["instances"] == 2 and blk["objects_per_instance"] == 2, blk
    assert blk["stride"] == 2, blk

    # summary is compact (no full object lists)
    sm = summary(res)
    assert "comm_objects" not in sm["devices"][0]

    # round-trip: emit YAML -> load as catalog -> decompose_device is catalog-exact
    cat = os.path.join(d, "cat.yaml")
    with open(cat, "w", encoding="utf-8") as fh:
        fh.write(to_catalog_yaml(res))
    os.environ["NICKOL_KNX_CATALOG"] = d
    dl._CATALOG_INDEX = None
    r = dl.decompose_device("TST-DIM2")
    assert r["source"] == "catalog-exact", r
    assert r["total_master_objects"] == 5, r
    os.environ.pop("NICKOL_KNX_CATALOG", None)
    dl._CATALOG_INDEX = None

print("OK — appprog_parser: order->app map, DPST->DPT, honest missing-DPT, block/stride, YAML round-trip")
