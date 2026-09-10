"""Evaluate the structure-first suggester on real projects against our name/Function
pairing engine (generate_ha) as the reference. Prints per-platform agreement and the
disagreements to inspect by hand. Only numbers, no project content, leave this machine."""
import sys, yaml
from collections import Counter
from xknxproject import XKNXProj
from nickol_knx_mcp.suggest import suggest_entities, _PRIMARY
from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.generate_ha import generate_ha_yaml

_REF_KEYS = {"light": ("address", "state_address", "brightness_address", "brightness_state_address"),
             "switch": ("address", "state_address"),
             "cover": ("move_long_address", "move_short_address", "stop_address", "position_address",
                       "position_state_address", "angle_address", "angle_state_address"),
             "climate": ("temperature_address", "target_temperature_address", "target_temperature_state_address",
                         "operation_mode_address")}
_UI = {"address": ("ga_switch", "write"), "state_address": ("ga_switch", "state"),
       "brightness_address": ("ga_brightness", "write"), "brightness_state_address": ("ga_brightness", "state"),
       "move_long_address": ("ga_up_down", "write"), "move_short_address": ("ga_step", "write"),
       "stop_address": ("ga_stop", "write"), "position_address": ("ga_position_set", "write"),
       "position_state_address": ("ga_position_state", "state"), "angle_address": ("ga_angle", "write"),
       "angle_state_address": ("ga_angle", "state"), "temperature_address": ("ga_temperature_current", "state"),
       "target_temperature_address": ("target_temperature.ga_temperature_target", "write"),
       "target_temperature_state_address": ("target_temperature.ga_temperature_target", "state"),
       "operation_mode_address": ("ga_operation_mode", "write")}
_PRIM_UI = {"light": ("ga_switch", "write"), "switch": ("ga_switch", "write"),
            "cover": ("ga_up_down", "write"), "climate": ("ga_temperature_current", "state"),
            "sensor": ("ga_sensor", "state"), "binary_sensor": ("ga_sensor", "state")}


def _get(conf, path, slot):
    node = conf
    for p in path.split("."):
        node = (node or {}).get(p)
    return (node or {}).get(slot)


def run(path, password=None, show=6):
    proj = XKNXProj(path, password).parse() if password else XKNXProj(path).parse()
    res = suggest_entities(proj, fallback=False)          # structural part only
    h = res["hints"]
    ref = yaml.safe_load(generate_ha_yaml(build_loaded_from_raw(proj, path))["yaml"]).get("knx") or {}
    ref_by = {}
    for plat, ents in ref.items():
        if plat in _PRIMARY and isinstance(ents, list):
            for e in ents:
                prim = next((e.get(k) for k in _PRIMARY[plat] if e.get(k)), None)
                if prim:
                    ref_by[prim] = (plat, e)
    n_dev = len(proj["devices"]); n_ch = sum(len(d["channels"]) for d in proj["devices"].values())
    print(f"\n=== {len(proj['group_addresses'])} GAs · {n_dev} devices · {n_ch} channels · "
          f"ETS {str(proj['info'].get('tool_version', '?'))[:3]} ===")
    print(f"structural: {h['structural']} entities + {h['sensors']} sensors (review-flagged {h['review']}, "
          f"FB-skipped {h['skipped_fb_covered']}) | reference (name engine): {len(ref_by)} entities")
    agree = Counter(); mism = []; only_struct = []; per_plat = Counter(); covered = set()
    for s in res["suggestions"]:
        plat0 = s["platform_options"][0]
        conf = s["suggestions"][plat0]["knx"]
        per_plat[plat0] += 1
        prim = _get(conf, *_PRIM_UI[plat0])
        covered.add(prim)
        if plat0 in ("sensor", "binary_sensor"):
            continue
        r = ref_by.get(prim)
        if not r:
            only_struct.append((plat0, prim, s["suggested_name"][:40]))
            continue
        rplat, rent = r
        same_plat = rplat == plat0 or {rplat, plat0} <= {"light", "switch"}
        keys_ok = keys_all = 0
        diffs = {}
        for k in _REF_KEYS.get(rplat, ()):
            if rent.get(k):
                keys_all += 1
                got = _get(conf, *_UI[k]) if k in _UI else None
                if got == rent[k]:
                    keys_ok += 1
                else:
                    diffs[k] = (rent[k], got)
        agree["entities"] += 1; agree["platform_ok"] += same_plat
        agree["keys_all"] += keys_all; agree["keys_ok"] += keys_ok
        if not same_plat or diffs:
            mism.append((plat0, rplat, prim, diffs))
    only_ref = [(p, a, e.get("name", "")[:40]) for a, (p, e) in ref_by.items() if a not in covered and p in _REF_KEYS]
    e = agree["entities"] or 1
    print(f"by platform: {dict(per_plat)}")
    print(f"structural ∩ reference: {agree['entities']} | platform agreement {agree['platform_ok']}/{agree['entities']} "
          f"({100*agree['platform_ok']/e:.0f} %) | address-key agreement {agree['keys_ok']}/{max(agree['keys_all'],1)} "
          f"({100*agree['keys_ok']/max(agree['keys_all'],1):.0f} %)")
    print(f"structure-only (channel found it, names didn't): {len(only_struct)} | reference-only (names found it, "
          f"no channel explains it): {len(only_ref)}")
    for row in mism[:show]:
        print("  MISMATCH", row[0], "vs ref", row[1], row[2], row[3])
    for row in only_struct[:show]:
        print("  STRUCT-ONLY", row)
    for row in only_ref[:show]:
        print("  REF-ONLY", row)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        run(p)
