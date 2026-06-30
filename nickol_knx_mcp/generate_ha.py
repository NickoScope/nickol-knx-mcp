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

# Venetian-blind slat (tilt) detection: a slat GA is the tilt of its parent
# blind, not a standalone cover.
_SLAT_WORDS = ("lamelle", "lamel", "ламел", "slat", "louver", "louvre", "tilt")
_DIR_WORDS = {"auf", "ab", "up", "down", "hoch", "runter", "move", "step",
              "long", "short", "open", "close", "вверх", "вниз"}
_BLIND_GENERIC = {"behang", "blind", "blinds", "shutter", "jalousie", "rollo",
                  "roller", "store", "markise", "roll", "cover", "curtain",
                  "штора", "жалюзи", "ролета", "ролл"}


def _is_slat(name: str) -> bool:
    low = name.lower()
    return any(w in low for w in _SLAT_WORDS)


def _ident_tokens(name: str) -> set:
    """Identity/zone tokens for matching a slat to its blind (drop direction,
    slat and generic-blind words so only the zone/name identity remains)."""
    return {t for t in base_tokens(name)
            if t not in _DIR_WORDS and t not in _SLAT_WORDS and t not in _BLIND_GENERIC}


_UPDOWN_PHRASES = ("up/down", "auf/ab", "ab/auf", "updown", "up-down", "вверх/вниз")
_STOP_WORDS = ("stop", "stopp", "стоп")


def _is_updown(name: str) -> bool:
    """A shutter move (long) command: 'up/down', 'auf/ab', or both directions."""
    low = name.lower()
    if any(p in low for p in _UPDOWN_PHRASES):
        return True
    toks = set(base_tokens(low))
    return ("up" in toks and "down" in toks) or ("auf" in toks and "ab" in toks)


def _is_stop(name: str) -> bool:
    low = name.lower()
    return any(w in low for w in _STOP_WORDS)


# Function words that differ between a command and its status (on/off, value,
# state, brightness, ...). Stripping them leaves the device/zone identity, so a
# command pairs to its feedback even when the identity is a single token
# (e.g. "HaloSpotLeft.A.VALUE" <-> "HaloSpotLeft.A.STATE%").
_FUNC_WORDS = {
    "on", "off", "onoff", "value", "val", "dim", "dimming", "bright", "brightness",
    "state", "status", "stat", "fb", "feedback", "rm", "pct", "percent",
    "up", "down", "move", "stop", "step", "pos", "position", "set", "control",
    "schalt", "schalten", "steuer", "wert", "helligkeit", "rueck", "rück", "soll",
    # colour function words: ignored so a colour GA pairs to its zone's light
    "colour", "color", "rgb", "rgbw", "rgbww", "hue", "saturation", "sat",
    "white", "warm", "cct", "kelvin", "temp", "temperature", "xyy", "farbe",
}


def _pair_ident(name: str) -> set:
    """Device/zone identity tokens for command<->status pairing."""
    return {t for t in base_tokens(name)
            if t not in _FUNC_WORDS and not t.endswith("%")}


def _identity_match(a_name: str, b_name: str) -> bool:
    """True when two names share the SAME device/zone identity.

    One identity must contain the other — a single shared zone token (e.g.
    "kitchen") is NOT enough. This stops a command from borrowing a sibling's
    status when it has none of its own (bug B1: "worktop LED" must not grab
    "island pendants" status just because both are "kitchen")."""
    a, b = _pair_ident(a_name), _pair_ident(b_name)
    if not a or not b:
        return False
    return a <= b or b <= a


# Colour command DPT -> (HA address key, HA state-address key).
_COLOUR_DPT: dict[tuple[int, int], tuple[str, str]] = {
    (232, 600): ("color_address", "color_state_address"),       # RGB
    (251, 600): ("rgbw_address", "rgbw_state_address"),          # RGBW
    (242, 600): ("xyy_address", "xyy_state_address"),            # xyY
}

# Words marking a target/setpoint temperature (vs the current room temperature).
_TARGET_WORDS = ("target", "setpoint", "soll", "sollwert", "уставк", "задан",
                 "целев", "зад.", "устав")

# HVAC function qualifiers stripped from a climate anchor's name to leave only
# the zone/location tokens — climate members (current temp, target, mode, valve)
# share the LOCATION, not the full identity, so they are gathered by location.
_CLIMATE_QUALIFIERS = {
    "hvac", "mode", "controller", "operation", "heat", "cool", "heating",
    "cooling", "climate", "thermostat", "ac", "тп", "режим", "отопл", "климат",
    "термостат", "конвектор", "тёплый", "теплый", "пол",
}


def _has(name: str, words) -> bool:
    low = name.lower()
    return any(w in low for w in words)


def generate_ha_yaml(project: LoadedProject) -> dict[str, Any]:
    """Return {'yaml': str, 'review': [...], 'counts': {...}}."""
    status_gas = [g for g in project.gas.values() if _is_status_ga(g)]
    fpairs = function_status_pairs(project)  # authoritative cmd-addr -> status-addr
    slat_addrs = {g.address for g in project.gas.values()
                  if g.category == "shutter" and _is_slat(g.name)}

    def status_for(cmd: GARecord):
        # 1. ETS Function role pairing is authoritative (names not needed).
        paired = fpairs.get(cmd.address)
        if paired and paired in project.gas:
            return project.gas[paired]
        # 2. fall back to name-token pairing.
        same_main = [s for s in status_gas if s.main == cmd.main]
        return find_status(cmd, same_main) or find_status(cmd, status_gas)

    def status_for_dpt(cmd: GARecord, want_main: int):
        """Find a status GA for cmd of a given DPT main, matched by device/zone
        identity. Lets a dimmable light find BOTH its on/off status (1.x) and
        brightness status (5.x), and pairs even when identity is a single token."""
        paired = fpairs.get(cmd.address)
        if paired and paired in project.gas and project.gas[paired].dpt_main == want_main:
            return project.gas[paired]
        cid = _pair_ident(cmd.name)
        if not cid:
            cands = [s for s in status_gas
                     if s.dpt_main == want_main and s.address not in consumed]
            same_main = [s for s in cands if s.main == cmd.main]
            return find_status(cmd, same_main) or find_status(cmd, cands)
        best, best_score = None, 0
        for s in status_gas:
            if s.dpt_main != want_main or s.address == cmd.address:
                continue
            if s.address in consumed:   # a status maps to exactly one entity
                continue
            # B1: require a full identity match, not just a shared zone token,
            # so a command never borrows a sibling's status.
            if not _identity_match(cmd.name, s.name):
                continue
            score = len(cid & _pair_ident(s.name)) + (2 if s.main == cmd.main else 0)
            if score > best_score:
                best, best_score = s, score
        return best

    def same_main_gas(cmd: GARecord):
        return [g for g in project.gas.values() if g.main == cmd.main]

    def attach_colour(entity: dict, ref: GARecord) -> None:
        """Attach RGB / RGBW / xyY / colour-temperature GAs (and their statuses)
        of the same zone identity to a light entity."""
        for sib in same_main_gas(ref):
            if sib.address in consumed or sib.kind != "command":
                continue
            if not _identity_match(ref.name, sib.name):
                continue
            key = (sib.dpt_main, sib.dpt_sub)
            if key in _COLOUR_DPT:
                a_key, s_key = _COLOUR_DPT[key]
                if a_key in entity:
                    continue
                entity[a_key] = sib.address
                consumed.add(sib.address)
                cst = status_for_dpt(sib, sib.dpt_main)
                if cst:
                    entity[s_key] = cst.address
                    consumed.add(cst.address)
            elif key == (7, 600) and "color_temperature_address" not in entity:
                entity["color_temperature_address"] = sib.address
                entity["color_temperature_mode"] = "absolute"
                consumed.add(sib.address)
                cst = status_for_dpt(sib, 7)
                if cst:
                    entity["color_temperature_state_address"] = cst.address
                    consumed.add(cst.address)

    switches: list[dict] = []
    binary_sensors: list[dict] = []
    sensors: list[dict] = []
    lights: list[dict] = []
    covers: list[dict] = []
    climates: list[dict] = []
    review: list[dict[str, Any]] = []
    consumed: set[str] = set()

    # ---- 1. COVERS first (they own 5.001 position) ----
    # A cover's "move long" is a shutter command that is up/down: canonical DPT
    # 1.008, OR a 1.x command whose name says up/down (real projects use 1.001).
    for ga in project.gas.values():
        if ga.address in consumed:
            continue
        is_move_long = (ga.category == "shutter" and ga.kind == "command"
                        and ga.dpt_main == 1 and ga.address not in slat_addrs
                        and (ga.dpt_sub == 8 or _is_updown(ga.name)))
        if not is_move_long:
            continue
        entity = {"name": ga.name, "move_long_address": ga.address}
        ptoks = _ident_tokens(ga.name)
        for sib in same_main_gas(ga):
            if sib.address in consumed or sib.address == ga.address:
                continue
            if sib.category != "shutter":
                continue
            # only attach siblings of the SAME shutter when both carry a zone
            # identity (prevents cross-wiring multiple blinds in one main group)
            if ptoks and _ident_tokens(sib.name) and not (ptoks & _ident_tokens(sib.name)):
                continue
            is_stop = (sib.dpt_main == 1 and sib.dpt_sub in (7, 10, 17)) or _is_stop(sib.name)
            if is_stop and "move_short_address" not in entity:
                entity["move_short_address"] = sib.address
                consumed.add(sib.address)
            elif sib.address in slat_addrs and sib.dpt_main == 1 \
                    and "move_short_address" not in entity:
                # venetian slat (tilt) = the short-move/step of this blind
                entity["move_short_address"] = sib.address
                consumed.add(sib.address)
            elif sib.dpt_main == 5 and sib.kind == "command" \
                    and "position_address" not in entity:
                entity["position_address"] = sib.address
                consumed.add(sib.address)
            elif sib.dpt_main == 5 and _is_status_ga(sib) \
                    and "position_state_address" not in entity:
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
            st5 = status_for_dpt(ga, 5)   # brightness status (5.x)
            if st5:
                entity["brightness_state_address"] = st5.address
                consumed.add(st5.address)
            for sib in same_main_gas(ga):
                if sib.address in consumed:
                    continue
                if sib.category == "lighting" and sib.dpt_main == 1 and sib.kind == "command" \
                        and _identity_match(ga.name, sib.name):
                    entity["address"] = sib.address
                    s1 = status_for_dpt(sib, 1)   # on/off status (1.x)
                    if s1:
                        entity["state_address"] = s1.address
                        consumed.add(s1.address)
                    consumed.add(sib.address)
                    break
            attach_colour(entity, ga)   # RGB/RGBW/xyY/colour-temp of this zone
            lights.append(entity)
            consumed.add(ga.address)

    # ---- 2b. Colour lights that have no separate 5.001 brightness channel ----
    for ga in project.gas.values():
        if ga.address in consumed:
            continue
        if ga.category != "lighting" or ga.kind != "command":
            continue
        if (ga.dpt_main, ga.dpt_sub) not in _COLOUR_DPT and (ga.dpt_main, ga.dpt_sub) != (7, 600):
            continue
        onoff = next((s for s in same_main_gas(ga)
                      if s.address not in consumed and s.dpt_main == 1 and s.dpt_sub == 1
                      and s.kind == "command" and _identity_match(ga.name, s.name)), None)
        if onoff is None:
            review.append({"reason": "color_light_without_switch", "address": ga.address,
                           "name": ga.name, "dpt": ga.dpt,
                           "hint": "Colour GA with no on/off switch in its zone — attach it "
                                   "to a light's color/rgbw address manually."})
            consumed.add(ga.address)
            continue
        entity = {"name": ga.name, "address": onoff.address}
        s1 = status_for_dpt(onoff, 1)
        if s1:
            entity["state_address"] = s1.address
            consumed.add(s1.address)
        consumed.add(onoff.address)
        attach_colour(entity, ga)
        lights.append(entity)

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
            st = status_for_dpt(ga, 1)
            if st:
                entity["state_address"] = st.address
                consumed.add(st.address)
            else:
                review.append({"reason": "switch_without_status",
                               "address": ga.address, "name": ga.name})
            switches.append(entity)
            consumed.add(ga.address)

    # ---- 3b. CLIMATE — anchored on an HVAC mode (DPT 20.102/20.105). Zone
    # members are matched project-wide by identity (the current temperature often
    # lives in a different main group than the mode). Emitted only when the HA-
    # required minimum is present (current temp + target-temp status); otherwise
    # the zone goes to review so we never write an invalid climate entity. ----
    built_climate: list[set] = []
    for ga in project.gas.values():
        if ga.address in consumed:
            continue
        if ga.category != "hvac" or ga.kind != "command" or ga.dpt_main != 20:
            continue
        zone_loc = _pair_ident(ga.name) - _CLIMATE_QUALIFIERS
        if zone_loc and any(zone_loc == d for d in built_climate):
            continue  # this zone already produced a climate entity
        zone = [g for g in project.gas.values()
                if g.address not in consumed and zone_loc and zone_loc <= _pair_ident(g.name)]

        def _pick(pred):
            return next((g for g in zone if pred(g)), None)

        # Temperature GAs must be DPT 9.001 specifically — DPT main 9 also covers
        # humidity (9.007), CO2 (9.008), lux (9.004); never treat those as a setpoint.
        cur = _pick(lambda g: (g.dpt_main, g.dpt_sub) == (9, 1) and g.kind == "sensor"
                    and not _has(g.name, _TARGET_WORDS))
        tgt_state = _pick(lambda g: (g.dpt_main, g.dpt_sub) == (9, 1) and _is_status_ga(g)
                          and _has(g.name, _TARGET_WORDS))
        tgt_cmd = _pick(lambda g: (g.dpt_main, g.dpt_sub) == (9, 1) and not _is_status_ga(g)
                        and _has(g.name, _TARGET_WORDS))
        op_cmd = _pick(lambda g: g.dpt_main == 20 and g.dpt_sub == 102 and g.kind == "command")
        op_state = _pick(lambda g: g.dpt_main == 20 and g.dpt_sub == 102 and _is_status_ga(g))
        ctrl_cmd = _pick(lambda g: g.dpt_main == 20 and g.dpt_sub == 105 and g.kind == "command")
        ctrl_state = _pick(lambda g: g.dpt_main == 20 and g.dpt_sub == 105 and _is_status_ga(g))
        valve = _pick(lambda g: g.dpt_main == 5 and _is_status_ga(g))

        if not (cur and tgt_state):
            review.append({"reason": "manual_climate", "address": ga.address,
                           "name": ga.name, "dpt": ga.dpt,
                           "hint": "HVAC mode found, but no clean current-temp + target-temp-"
                                   "status pair in this zone — map the climate entity manually."})
            consumed.add(ga.address)
            continue

        ent = {"name": ga.name,
               "temperature_address": cur.address,
               "target_temperature_state_address": tgt_state.address}
        if tgt_cmd:
            ent["target_temperature_address"] = tgt_cmd.address
        if op_cmd:
            ent["operation_mode_address"] = op_cmd.address
        if op_state:
            ent["operation_mode_state_address"] = op_state.address
        if ctrl_cmd:
            ent["controller_mode_address"] = ctrl_cmd.address
        if ctrl_state:
            ent["controller_mode_state_address"] = ctrl_state.address
        if valve:
            ent["command_value_state_address"] = valve.address
        for m in (cur, tgt_state, tgt_cmd, op_cmd, op_state, ctrl_cmd, ctrl_state, valve):
            if m:
                consumed.add(m.address)
        climates.append(ent)
        if zone_loc:
            built_climate.append(zone_loc)

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
        elif ga.ha_platform in ("climate", "scene", "number", "datetime", "text"):
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
        # A slat/tilt GA that wasn't matched to a blind cover by name.
        if ga.address in slat_addrs:
            item["reason"] = "shutter_slat_unattached"
            item["hint"] = ("Slat/tilt control of a venetian blind; could not be matched "
                            "to a blind cover by name. Attach it manually as the cover's "
                            "tilt/move_short address.")
        # A shutter-looking command that didn't become a cover almost always has
        # an incomplete DPT (e.g. bare "1" instead of 1.008 up/down). Make that
        # actionable instead of an opaque drop.
        elif ga.category == "shutter" and ga.kind == "command" and ga.dpt_sub is None:
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
    if climates:
        knx["climate"] = climates
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
        "climate": len(climates),
        "binary_sensor": len(binary_sensors), "sensor": len(sensors),
        "review": len(review),
    }
    return {"yaml": text, "review": review, "counts": counts}
