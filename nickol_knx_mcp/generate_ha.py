"""Generate a Home Assistant KNX package (YAML) from the parsed project.

Conservative by design: emits switch / binary_sensor / sensor / light / cover
entities only when command+status pairing is reasonably certain, and routes
everything ambiguous (climate, scenes, multi-GA fixtures) to a 'review' list the
caller surfaces in the report. Pairing is name-token based (see pairing.py), so
status GAs in a separate middle group are still matched.
"""

from __future__ import annotations

from typing import Any

import yaml

from .project import LoadedProject, GARecord
from .analyze import _is_status_ga
from .pairing import find_status, base_tokens, function_status_pairs


def generate_ha_yaml(project: LoadedProject) -> dict[str, Any]:
    """Return {'yaml': str, 'review': [...], 'counts': {...}}."""
    status_gas = [g for g in project.gas.values() if _is_status_ga(g)]
    fpairs = function_status_pairs(project)  # authoritative cmd-addr -> status-addr

    def status_for(cmd: GARecord):
        # 1. ETS Function role pairing is authoritative (names not needed).
        paired = fpairs.get(cmd.address)
        if paired and paired in project.gas:
            return project.gas[paired]
        # 2. fall back to name-token pairing.
        same_main = [s for s in status_gas if s.main == cmd.main]
        return find_status(cmd, same_main) or find_status(cmd, status_gas)

    def same_main_gas(cmd: GARecord):
        return [g for g in project.gas.values() if g.main == cmd.main]

    switches: list[dict] = []
    binary_sensors: list[dict] = []
    sensors: list[dict] = []
    lights: list[dict] = []
    covers: list[dict] = []
    review: list[dict[str, Any]] = []
    consumed: set[str] = set()

    # ---- 1. COVERS first (they own 5.001 position) ----
    for ga in project.gas.values():
        if ga.address in consumed:
            continue
        if ga.category == "shutter" and ga.dpt_main == 1 and ga.dpt_sub == 8:
            entity = {"name": ga.name, "move_long_address": ga.address}
            for sib in same_main_gas(ga):
                if sib.address in consumed or sib.address == ga.address:
                    continue
                if sib.category != "shutter":
                    continue
                if sib.dpt_main == 1 and sib.dpt_sub == 10:
                    entity["move_short_address"] = sib.address
                    consumed.add(sib.address)
                elif sib.dpt_main == 5 and sib.kind == "command":
                    entity["position_address"] = sib.address
                    consumed.add(sib.address)
                elif sib.dpt_main == 5 and _is_status_ga(sib):
                    entity["position_state_address"] = sib.address
                    consumed.add(sib.address)
            covers.append(entity)
            consumed.add(ga.address)
            review.append({"reason": "verify_cover_mapping", "address": ga.address,
                           "name": ga.name})

    # ---- 2. LIGHTS (brightness 5.001 command, lighting category) ----
    for ga in project.gas.values():
        if ga.address in consumed:
            continue
        if ga.category == "lighting" and ga.dpt_main == 5 and ga.kind == "command":
            entity = {"name": ga.name, "brightness_address": ga.address}
            st = status_for(ga)
            if st and st.dpt_main == 5:
                entity["brightness_state_address"] = st.address
                consumed.add(st.address)
            for sib in same_main_gas(ga):
                if sib.address in consumed:
                    continue
                if sib.category == "lighting" and sib.dpt_main == 1 and sib.kind == "command" \
                        and len(base_tokens(ga.name) & base_tokens(sib.name)) >= 2:
                    entity["address"] = sib.address
                    s2 = status_for(sib)
                    if s2 and s2.dpt_main == 1:
                        entity["state_address"] = s2.address
                        consumed.add(s2.address)
                    consumed.add(sib.address)
                    break
            lights.append(entity)
            consumed.add(ga.address)

    # ---- 3. SWITCHES (1.001 command) ----
    for ga in project.gas.values():
        if ga.address in consumed:
            continue
        if ga.dpt_main == 1 and ga.dpt_sub == 1 and ga.kind == "command" \
                and ga.category in ("lighting", "unknown"):
            if not ga.name.strip():
                review.append({"reason": "switch_unnamed", "address": ga.address, "name": ""})
                consumed.add(ga.address)
                continue
            entity = {"name": ga.name, "address": ga.address}
            st = status_for(ga)
            if st and st.dpt_main == 1:
                entity["state_address"] = st.address
                consumed.add(st.address)
            else:
                review.append({"reason": "switch_without_status",
                               "address": ga.address, "name": ga.name})
            switches.append(entity)
            consumed.add(ga.address)

    # ---- 4. SENSORS / BINARY SENSORS (read-only) ----
    for ga in project.gas.values():
        if ga.address in consumed:
            continue
        if ga.ha_platform == "sensor":
            entity = {"name": ga.name, "state_address": ga.address}
            if ga.value_type:
                entity["type"] = ga.value_type
            else:
                review.append({"reason": "sensor_without_value_type",
                               "address": ga.address, "name": ga.name})
            sensors.append(entity)
            consumed.add(ga.address)
        elif ga.ha_platform == "binary_sensor":
            binary_sensors.append({"name": ga.name, "state_address": ga.address})
            consumed.add(ga.address)
        elif ga.ha_platform in ("climate", "scene", "number"):
            review.append({"reason": f"manual_{ga.ha_platform}", "address": ga.address,
                           "name": ga.name, "dpt": ga.dpt})
        elif ga.ha_platform == "unknown" and ga.dpt_main is not None:
            review.append({"reason": "unmapped_dpt", "address": ga.address,
                           "name": ga.name, "dpt": ga.dpt})

    # ---- 5. Catch-all: never drop a GA silently ("no silent caps") ----
    accounted: set[str] = set(consumed)
    accounted.update(r["address"] for r in review if r.get("address"))
    for addr, ga in project.gas.items():
        if addr in accounted:
            continue
        item = {
            "reason": "not_mapped",
            "address": addr, "name": ga.name, "dpt": ga.dpt,
            "category": ga.category, "kind": ga.kind,
        }
        # A shutter-looking command that didn't become a cover almost always has
        # an incomplete DPT (e.g. bare "1" instead of 1.008 up/down). Make that
        # actionable instead of an opaque drop.
        if ga.category == "shutter" and ga.kind == "command" and ga.dpt_sub is None:
            item["reason"] = "shutter_incomplete_dpt"
            item["hint"] = ("Looks like a shutter control but the DPT has no sub-type. "
                            "Set it in ETS (1.008 up/down, 1.010 stop, 5.001 position) "
                            "so it can map to a Home Assistant cover.")
        review.append(item)

    knx: dict[str, Any] = {}
    if switches:
        knx["switch"] = switches
    if lights:
        knx["light"] = lights
    if covers:
        knx["cover"] = covers
    if binary_sensors:
        knx["binary_sensor"] = binary_sensors
    if sensors:
        knx["sensor"] = sensors

    package = {"knx": knx}
    text = (
        "# Home Assistant KNX package generated by nickol-knx-mcp\n"
        f"# Source project: {project.info.get('name', '?')}\n"
        "# REVIEW before use: command/status pairing is inferred heuristically.\n"
        "# Multi-GA fixtures (light/cover/climate) and scenes need manual verification.\n"
        f"# {len(review)} group address(es) need manual review (see the 'review' list); "
        "nothing is dropped silently.\n\n"
        + yaml.safe_dump(package, allow_unicode=True, sort_keys=False, default_flow_style=False)
    )
    counts = {
        "switch": len(switches), "light": len(lights), "cover": len(covers),
        "binary_sensor": len(binary_sensors), "sensor": len(sensors),
        "review": len(review),
    }
    return {"yaml": text, "review": review, "counts": counts}
