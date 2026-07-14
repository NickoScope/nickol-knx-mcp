"""Synthetic test for cross-device parameter outlier detection (check_device_parameters).

Builds an in-memory .knxproj (a ZIP with a P-*/0.xml project part and a tiny
application program) containing 5 identical devices where one has an odd value,
one parameter that is balanced-split, and one that is uniform — then asserts the
tool flags the outlier, resolves its name, classifies the split, and stays quiet
on the uniform one.
"""
import io
import zipfile

from nickol_knx_mcp.param_check import check_device_parameters

HP = "M-TEST_H-X-1_HP-1111"


def _device(addr, hyst, mode, split):
    pirs = "".join([
        f'<ParameterInstanceRef RefId="M-TEST_A-1111_P-1_R-1" Value="{hyst}" />',
        f'<ParameterInstanceRef RefId="M-TEST_A-1111_P-2_R-2" Value="{mode}" />',
        f'<ParameterInstanceRef RefId="M-TEST_A-1111_P-3_R-3" Value="{split}" />',
    ])
    return (f'<DeviceInstance Id="P-TEST-0_DI-{addr}" Address="{addr}" Name="Th{addr}" '
            f'Hardware2ProgramRefId="{HP}" ProductRefId="M-TEST_H-X-1_P-TVALVE">'
            f'{pirs}</DeviceInstance>')


def _make_knxproj() -> str:
    # 5 identical devices: hysteresis 5,5,5,5,10 (dev .10 is the outlier);
    # mode uniform (2); split 1,1,1,2,2 (balanced 3/2)
    devs = [
        _device(1, 5, 2, 1), _device(2, 5, 2, 1), _device(3, 5, 2, 1),
        _device(4, 5, 2, 2), _device(10, 10, 2, 2),
    ]
    proj0 = ('<?xml version="1.0" encoding="utf-8"?>'
             '<KNX xmlns="http://knx.org/xml/project/20"><Project><Installations>'
             '<Installation><Topology><Area><Line>'
             + "".join(devs) +
             '</Line></Area></Topology></Installation></Installations></Project></KNX>')
    app = ('<?xml version="1.0" encoding="utf-8"?><KNX><ManufacturerData><Manufacturer>'
           '<ApplicationPrograms><ApplicationProgram Id="M-TEST_A-1111">'
           '<ParameterRefs>'
           '<ParameterRef Id="M-TEST_A-1111_P-1_R-1" RefId="M-TEST_A-1111_P-1" />'
           '<ParameterRef Id="M-TEST_A-1111_P-3_R-3" RefId="M-TEST_A-1111_P-3" />'
           '</ParameterRefs>'
           '<Parameters>'
           '<Parameter Id="M-TEST_A-1111_P-1" Name="Hysteresis (K)" />'
           '<Parameter Id="M-TEST_A-1111_P-3" Name="Zone role" />'
           '</Parameters>'
           '</ApplicationProgram></ApplicationPrograms></Manufacturer></ManufacturerData></KNX>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("P-TEST/0.xml", proj0)
        z.writestr("M-TEST/M-TEST_A-1111.xml", app)
    path = "/tmp/_paramcheck_test.knxproj"
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


def main():
    path = _make_knxproj()
    r = check_device_parameters(path, min_group=3)
    assert "error" not in r, r
    assert r["devices"] == 5, r["devices"]
    assert r["identical_device_groups"] == 1, r

    # clear outlier: hysteresis 4x5 vs 1x10, resolved name, odd device addr 10
    hits = [o for o in r["clear_outliers"] if o["refid"].endswith("R-1")]
    assert hits, f"hysteresis outlier not found: {r['clear_outliers']}"
    h = hits[0]
    assert h["parameter"] == "Hysteresis (K)", h["parameter"]
    assert h["name_resolved"] is True
    assert h["numeric"] is True
    assert h["majority_value"] == "5"
    assert [d["value"] for d in h["odd_devices"]] == ["10"], h["odd_devices"]
    assert h["odd_devices"][0]["address"] == "10"
    # significance: "Hysteresis (K)" is a config VALUE -> shows up in focus
    assert h["significance"] == "config_value", h["significance"]
    assert r["focus_count"] >= 1
    assert any(o["refid"].endswith("R-1") for o in r["focus"]), r["focus"]

    # uniform param (mode, all "2") must NOT appear anywhere
    assert not any(o["refid"].endswith("R-2") for o in r["clear_outliers"] + r["split_configs"])

    # balanced split (1,1,1,2,2) -> split_configs, name resolved
    splits = [o for o in r["split_configs"] if o["refid"].endswith("R-3")]
    assert splits, f"split not found: {r['split_configs']}"
    assert splits[0]["parameter"] == "Zone role"
    variants = {v["value"]: v["count"] for v in splits[0]["variants"]}
    assert variants == {"1": 3, "2": 2}, variants

    print("test_param_check: OK — outlier flagged (Hysteresis 4x5 vs 1x10 @ addr 10), "
          "uniform param quiet, balanced split classified, names resolved.")


if __name__ == "__main__":
    main()
