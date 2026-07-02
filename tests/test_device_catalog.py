"""decompose_device: generic-recipe fallback + opt-in local exact catalog.

Self-contained: builds a tiny synthetic catalog in a temp dir, so the test does
NOT depend on any locally-harvested (unshipped) catalog data.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nickol_knx_mcp.device_library as dl

SAMPLE_CATALOG = """\
schema_version: "0.1"
manufacturer: "TestVendor"
devices:
  - order_number: "TV-DIM4"
    name: "TestDimmer 4CH"
    category: "actuator/dimmer"
    application_program: { name: "TestDimmer", version: "v3" }
    channels: { dimmer_channels: 4 }
    object_counts: { master_catalog_total: 92 }
    repeating_blocks:
      - unit: "dimmer_channel"
        instances: 4
        objects_per_instance: 5
        stride: 5
        objects:
          - { number: 1, name: "[C1] On/Off", dpt: "1.001", role: cmd, size_bits: 1 }
          - { number: 2, name: "[C1] On/Off (Status)", dpt: "1.001", role: status, size_bits: 1 }
          - { number: 3, name: "[C1] Relative Dimming", dpt: "3.007", role: cmd, size_bits: 4 }
          - { number: 4, name: "[C1] Absolute Dimming", dpt: "5.001", role: cmd, size_bits: 8 }
          - { number: 5, name: "[C1] Pattern", role: cmd, size_bits: 8 }   # no dpt -> stays None
"""


def _reset(catalog_path=None):
    if catalog_path:
        os.environ["NICKOL_KNX_CATALOG"] = catalog_path
    else:
        os.environ.pop("NICKOL_KNX_CATALOG", None)
    dl._CATALOG_INDEX = None  # drop the module cache between modes


# 1) No catalog configured -> generic recipe, behaviour unchanged
_reset()
r = dl.decompose_device("ZIO-MB24", 2)
assert r["matched"] and r["source"] == "recipe-approximate", r
assert r["total_ga"] == r["objects_per_unit"] * 2, r

r = dl.decompose_device("no-such-device")
assert r["matched"] is False and r["source"] == "recipe-approximate", r

# 2) Local catalog configured -> exact model, matched by order number AND by name
with tempfile.TemporaryDirectory() as d:
    with open(os.path.join(d, "vendor.yaml"), "w", encoding="utf-8") as fh:
        fh.write(SAMPLE_CATALOG)
    _reset(d)

    for q in ("TV-DIM4", "tv-dim4", "TestDimmer 4CH", "testdimmer 4ch"):
        r = dl.decompose_device(q)
        assert r["source"] == "catalog-exact", (q, r["source"])
        assert r["order_number"] == "TV-DIM4", (q, r)
        assert r["application_program"]["version"] == "v3", r
        assert r["total_master_objects"] == 92, r
        blk = r["blocks"][0]
        assert blk["unit"] == "dimmer_channel" and blk["instances"] == 4, blk
        assert blk["objects_per_instance"] == 5, blk
        assert blk["first_instance_objects"][0]["dpt"] == "1.001", blk
        assert blk["first_instance_objects"][4]["dpt"] is None, "no DPT must stay None, never guessed"

    # a device NOT in the catalog still falls back to the generic recipe
    r = dl.decompose_device("dimmer")
    assert r["source"] == "recipe-approximate" and r["matched"], r

# 3) env cleared -> back to recipe-only, no stale cache
_reset()
assert dl.decompose_device("TV-DIM4")["matched"] is False

print("OK — device catalog wiring: recipe fallback + catalog-exact + name match + honest unverified DPT")
