"""Entity suggestions from project STRUCTURE — prototype of a second Home Assistant
KNX ``SuggestionProvider`` (core PR #180891 defines the contract; this module mirrors
its result shape so it can be ported into ``storage/entity_suggestions/`` as-is).

Order of evidence (deliberately NOT names-first — the FB provider's own test fixture
names its group addresses "GA 1/0/1", so a name-first engine is blind there):

  1. **device channel** — ``devices[*].channels[*].communication_object_ids`` →
     ``communication_objects[*].group_address_links`` gives the GA set of one
     actuator channel; object **flags** say what each GA is: ``write`` = the device
     receives commands on it, ``transmit`` (without ``write``) = the device reports
     state on it;
  2. **DPT pattern inside the channel** — 1.008 (+1.007/1.010/1.017, 5.001) is a
     cover; 1.001 (+5.001, colour DPTs) is a light/switch; 9.001 state + 9.001/6.010
     command (+20.102) is a climate; state-only channels are sensors;
  3. **names** — only as a tie-break (socket vs light, slat vs position) and always
     recorded in ``metadata.review`` so the panel can ask for confirmation.

Channels the FB provider already covers (functional blocks 417/418/422/423/427/800,
HA ``storage/dpa.py``) are skipped — the orchestrator does not de-duplicate across
providers. Group addresses no channel explains fall back to the name/Function
pairing engine of :mod:`generate_ha` (tier ``heuristic``).

Pure functions, no HA imports — the HA provider class is a ~30-line wrapper.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Optional, cast

import yaml

from .project import build_loaded_from_raw
from .generate_ha import generate_ha_yaml

PROVIDER_ID = "structure"
# functional blocks the HA FB provider turns into suggestions (storage/dpa.py, PR #180891)
FB_COVERED = frozenset({"417", "418", "422", "423", "427", "800"})

_SWITCH_WORDS = ("socket", "steckdose", "розетк", "pump", "pumpe", "насос", "valve", "ventil",
                 "клапан", "outlet", "relay", "реле", "boiler", "бойлер", "heizung", "heater")
_SLAT_WORDS = ("slat", "lamell", "tilt", "angle", "ламел", "угол", "наклон")
_INPUT_WORDS = ("input", "eingang", "вход", "detector", "датчик", "sensor", "taster", "button", "кнопк")
_SETPOINT_WORDS = ("setpoint", "sollwert", "уставк", "задан", "target", "set point", "consigne")
_COLOR_DPTS = {(232, 600): "232.600", (251, 600): "251.600", (242, 600): "242.600"}
_COLOR_TEMP_DPTS = {(7, 600): "7.600", (9, 2): "9.002"}


def _dpt(ga: dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    d = ga.get("dpt") or {}
    return d.get("main"), d.get("sub")


def _dpt_str(ga: dict[str, Any]) -> Optional[str]:
    m, s = _dpt(ga)
    if m is None:
        return None
    return f"{m}.{s:03d}" if s is not None else str(m)


def _has(name: str, words) -> bool:
    low = (name or "").lower()
    return any(w in low for w in words)


class _Link:
    """One (communication object → primary group address) link with its role."""
    __slots__ = ("co_id", "ga", "passive", "dpt", "name", "role", "text")

    def __init__(self, co_id: str, ga: str, passive: list[str], dpt, name: str, role: str, text: str):
        self.co_id, self.ga, self.passive, self.dpt, self.name, self.role, self.text = \
            co_id, ga, passive, dpt, name, role, text


def _role(co: dict[str, Any]) -> str:
    """``sink`` = device receives commands on the GA (write flag only);
    ``source`` = device reports on it (transmit/read, no write);
    ``dual`` = both (push-button rockers with LED feedback, some vendors' inputs) —
    dual objects never create or complete an entity: they are the *other* side."""
    fl = co.get("flags") or {}
    w, t, r = bool(fl.get("write")), bool(fl.get("transmit")), bool(fl.get("read"))
    return "dual" if (w and (t or r)) else "sink" if w else "source" if (t or r) else "none"


def _links_of(project: dict[str, Any], co_ids, shared: Optional[set[str]] = None) -> list[_Link]:
    """Links of a set of communication objects (see :func:`_role`). ``shared`` GAs
    (reported by several channels) are never usable as an entity's state."""
    gas = project["group_addresses"]
    cos = project["communication_objects"]
    out: list[_Link] = []
    for cid in co_ids:
        co = cos.get(cid)
        if not co:
            continue
        links = [a for a in (co.get("group_address_links") or []) if a in gas]
        if not links:
            continue
        role = _role(co)
        if role in ("none", "dual"):
            continue
        if role == "source" and shared and links[0] in shared:
            continue
        ga = gas[links[0]]
        text = " ".join(x for x in (co.get("text"), co.get("function_text"), co.get("name")) if x)
        out.append(_Link(cid, links[0], links[1:], _dpt(ga), ga.get("name") or "", role, text))
    return out


_SUBUNIT_RE = re.compile(r"^\s*\[([^\]]{1,6})\]")
# object texts that describe the device's own health/plumbing, not a building sensor
_DIAG_WORDS = ("error", "fehler", "diagnos", "heartbeat", "watchdog", "alive", "version",
               "firmware", "communication fail", "bus voltage", "reset", "scene number",
               "identification", "störung", "ошибк", "авари", "диагност")


def _subunit(link: "_Link") -> Optional[str]:
    """Vendor sub-unit marker of a communication object, e.g. "[2] Switch On/Off" -> "2".

    Multi-output actuators (Zennio Lumento/MAXinBOX, many others) put every output of a
    device into ONE ETS channel and separate them only in the object text. Without this
    split a 4-output dimmer looks like one channel with four switch commands, the channel
    is abandoned, and all of its status objects fall through to sensor suggestions.
    """
    m = _SUBUNIT_RE.match(link.text or "")
    return m.group(1).strip() if m else None


def _split_subunits(links: list["_Link"]) -> list[tuple[Optional[str], list["_Link"]]]:
    """Split a channel into vendor sub-units; [(None, links)] when there is nothing to split."""
    groups: dict[str, list[_Link]] = defaultdict(list)
    loose: list[_Link] = []
    for l in links:
        t = _subunit(l)
        (groups[t] if t else loose).append(l)
    if len(groups) < 2:
        return [(None, links)]
    out: list[tuple[Optional[str], list[_Link]]] = [(t, ls) for t, ls in groups.items()]
    if loose:
        # objects without a marker (device-wide: errors, scene, temperature) stay separate
        out.append((None, loose))
    return out


def _pick(links: list[_Link], want: str, pred, used: set[str]) -> list[_Link]:
    """Links matching ``pred`` in role preference for ``want`` ('sink' or 'source');
    ``dual`` links serve as the missing side. Never reuses a GA."""
    return [l for l in links if l.role == want and pred(l) and l.ga not in used]


def _ga_conf(link: _Link, slot: str, dpt: Optional[str] = None) -> dict[str, Any]:
    d: dict[str, Any] = {slot: link.ga}
    if link.passive:
        d["passive"] = list(link.passive)
    if dpt:
        d["dpt"] = dpt
    return d


def _merge(conf: dict[str, Any], link: _Link, slot: str) -> None:
    conf[slot] = link.ga
    if link.passive:
        conf.setdefault("passive", [])
        conf["passive"].extend(a for a in link.passive if a not in conf["passive"])


def _is1(l: _Link, sub=None) -> bool:
    return l.dpt[0] == 1 and (sub is None or l.dpt[1] in sub)


def _classify_channel(project: dict[str, Any], links: list[_Link], chan_name: str
                      ) -> Optional[tuple[list[str], dict[str, dict[str, Any]], dict[str, Any]]]:
    """→ (platform_options, {platform: knx-config}, metadata) or None."""
    sinks = [l for l in links if l.role == "sink"]
    if not sinks:
        return None
    used: set[str] = set()
    review: list[str] = []
    evidence: list[str] = ["channel", "flags", "dpt"]
    meta = {"tier": "structural", "evidence": evidence, "review": review}

    # ── cover: an up/down 1.008 sink is unambiguous ──────────────────────────
    updown = _pick(links, "sink", lambda l: l.dpt == (1, 8), used)
    if updown:
        knx: dict[str, Any] = {"ga_up_down": _ga_conf(updown[0], "write")}
        used.add(updown[0].ga)
        for l in _pick(links, "sink", lambda l: l.dpt in ((1, 7), (1, 17)), used)[:1]:
            knx["ga_step"] = _ga_conf(l, "write"); used.add(l.ga)
        for l in _pick(links, "sink", lambda l: l.dpt == (1, 10), used)[:1]:
            knx["ga_stop"] = _ga_conf(l, "write"); used.add(l.ga)
        pos_cmd = _pick(links, "sink", lambda l: l.dpt == (5, 1), used)
        pos_st = _pick(links, "source", lambda l: l.dpt == (5, 1), used)
        # slat vs position: a name saying "slat/lamelle" wins, else order (first = position)
        def _split(cands):
            slats = [l for l in cands if _has(l.name, _SLAT_WORDS)]
            pos = [l for l in cands if l not in slats]
            if slats:
                evidence.append("name:slat")
            return (pos[:1], (slats or pos[1:])[:1])
        p_cmd, a_cmd = _split(pos_cmd)
        p_st, a_st = _split(pos_st)
        if p_cmd:
            knx["ga_position_set"] = _ga_conf(p_cmd[0], "write"); used.add(p_cmd[0].ga)
        if p_st:
            knx["ga_position_state"] = _ga_conf(p_st[0], "state"); used.add(p_st[0].ga)
        if a_cmd or a_st:
            ang: dict[str, Any] = {}
            if a_cmd:
                _merge(ang, a_cmd[0], "write"); used.add(a_cmd[0].ga)
            if a_st:
                _merge(ang, a_st[0], "state"); used.add(a_st[0].ga)
            knx["ga_angle"] = ang
            if not any(_has(l.name, _SLAT_WORDS) for l in (a_cmd + a_st)):
                review.append("second 5.001 taken as slat angle by order, not by name")
        return (["cover"], {"cover": knx}, meta)

    # ── climate: any 9.001 object makes this a thermostat/valve channel, never a light.
    #    Vendor object texts (app-program semantics, not integrator naming) tell
    #    setpoint from measured temperature.
    t_all = [l for l in links if l.dpt == (9, 1)]
    if t_all:
        if any(_has(l.text, _SETPOINT_WORDS) for l in t_all):
            def _is_setpoint(l): return _has(l.text, _SETPOINT_WORDS)
            t_cur = [l for l in t_all if not _is_setpoint(l)]
            t_cur_src = [l for l in t_cur if l.role == "source"] + [l for l in t_cur if l.role == "sink"]
            sp_cmd = [l for l in t_all if l.role == "sink" and _is_setpoint(l)]
            sp_st = [l for l in t_all if l.role == "source" and _is_setpoint(l)]
        else:
            # no vendor texts: by role — a thermostat RECEIVES its setpoint and REPORTS
            # the measured temperature; a second reported 9.001 is the setpoint status
            srcs = [l for l in t_all if l.role == "source"]
            sp_cmd = [l for l in t_all if l.role == "sink"]
            t_cur_src, sp_st = srcs[:1], srcs[1:2]
        shift = _pick(links, "sink", lambda l: l.dpt in ((6, 10), (9, 2)), used)
        if not sp_cmd and not shift:
            # a plain sensor channel (temperature + maybe humidity): sensors only
            return None
        if not t_cur_src:
            review.append("setpoint present but no measured-temperature object in the channel")
            return None
        evidence.append("object_text")
        cur = t_cur_src[0]
        knx = {"ga_temperature_current": _ga_conf(cur, "state")}; used.add(cur.ga)
        if cur.role == "sink":
            review.append("measured temperature taken from the thermostat's external-sensor INPUT object")
        if sp_cmd:
            tgt = _ga_conf(sp_cmd[0], "write"); used.add(sp_cmd[0].ga)
            if sp_st:
                _merge(tgt, sp_st[0], "state"); used.add(sp_st[0].ga)
            knx["target_temperature"] = {"ga_temperature_target": tgt}
        else:
            if not sp_st:
                review.append("setpoint shift without a setpoint status object")
                return None
            sh = _ga_conf(shift[0], "write", f"{shift[0].dpt[0]}.{shift[0].dpt[1]:03d}"); used.add(shift[0].ga)
            for x in _pick(links, "source", lambda l: l.dpt == shift[0].dpt, used)[:1]:
                _merge(sh, x, "state"); used.add(x.ga)
            knx["target_temperature"] = {"ga_temperature_target": _ga_conf(sp_st[0], "state"),
                                         "ga_setpoint_shift": sh}
            used.add(sp_st[0].ga)
        for l in _pick(links, "sink", lambda l: l.dpt == (20, 102), used)[:1]:
            knx["ga_operation_mode"] = _ga_conf(l, "write"); used.add(l.ga)
            for x in _pick(links, "source", lambda y: y.dpt == (20, 102), used)[:1]:
                _merge(knx["ga_operation_mode"], x, "state"); used.add(x.ga)
        for l in _pick(links, "sink", lambda l: l.dpt == (1, 100), used)[:1]:
            knx["ga_heat_cool"] = _ga_conf(l, "write"); used.add(l.ga)
        for l in _pick(links, "sink", lambda l: _is1(l, (1, None)), used)[:1]:
            knx["ga_on_off"] = _ga_conf(l, "write"); used.add(l.ga)
            for x in _pick(links, "source", lambda y: _is1(y, (1, 11, None)), used)[:1]:
                _merge(knx["ga_on_off"], x, "state"); used.add(x.ga)
        for l in _pick(links, "source", lambda l: l.dpt == (5, 1), used)[:1]:
            knx["ga_valve"] = _ga_conf(l, "state"); used.add(l.ga)
        return (["climate"], {"climate": knx}, meta)

    # ── light / switch: a 1.001 (or bare 1.x) sink ──────────────────────────
    on_cmd = _pick(links, "sink", lambda l: _is1(l, (1, None)), used)
    bri_cmd = _pick(links, "sink", lambda l: l.dpt == (5, 1), used)
    col_cmd = _pick(links, "sink", lambda l: l.dpt in _COLOR_DPTS, used)
    ct_cmd = _pick(links, "sink", lambda l: l.dpt in _COLOR_TEMP_DPTS, used)
    if on_cmd or bri_cmd or col_cmd:
        if len({l.ga for l in on_cmd}) > 1:
            # several independent switch commands in one channel: not one entity
            review.append("channel carries several switch commands; split by name pairing")
            return None
        knx = {}
        if on_cmd:
            knx["ga_switch"] = _ga_conf(on_cmd[0], "write"); used.add(on_cmd[0].ga)
            for l in _pick(links, "source", lambda l: _is1(l, (1, 11, None)), used)[:1]:
                _merge(knx["ga_switch"], l, "state"); used.add(l.ga)
        if bri_cmd:
            knx["ga_brightness"] = _ga_conf(bri_cmd[0], "write"); used.add(bri_cmd[0].ga)
            for l in _pick(links, "source", lambda l: l.dpt == (5, 1), used)[:1]:
                _merge(knx["ga_brightness"], l, "state"); used.add(l.ga)
        if ct_cmd:
            l = ct_cmd[0]
            knx["ga_color_temp"] = _ga_conf(l, "write", _COLOR_TEMP_DPTS[l.dpt]); used.add(l.ga)
            for s in _pick(links, "source", lambda x: x.dpt == l.dpt, used)[:1]:
                _merge(knx["ga_color_temp"], s, "state"); used.add(s.ga)
        if col_cmd:
            l = col_cmd[0]
            c = _ga_conf(l, "write", _COLOR_DPTS[l.dpt]); used.add(l.ga)
            for s in _pick(links, "source", lambda x: x.dpt == l.dpt, used)[:1]:
                _merge(c, s, "state"); used.add(s.ga)
            knx["color"] = {"ga_color": c}
        if "ga_switch" not in knx and "color" not in knx:
            # brightness-only: HA light needs ga_switch or individual colours
            review.append("dimmer without a switch object: light schema needs ga_switch")
            return None
        options = ["light"]
        out = {"light": knx}
        if "ga_switch" in knx and not bri_cmd and not col_cmd and not ct_cmd:
            sw = {"ga_switch": knx["ga_switch"]}
            names = " ".join([chan_name] + [l.name for l in links])
            if _has(names, _SWITCH_WORDS):
                evidence.append("name:switch")
                options = ["switch", "light"]
            else:
                options = ["light", "switch"]
                review.append("plain 1.001 channel: light or switch decided by name only")
            out["switch"] = sw
        return (options, out, meta)

    return None


def _sensor_suggestions(project: dict[str, Any], links: list[_Link], sink_gas: set[str],
                        skipped: Optional[list] = None
                        ) -> list[tuple[list[str], dict[str, dict[str, Any]], dict[str, Any], _Link]]:
    """State-only channels (no sink anywhere for the GA) → sensor / binary_sensor per GA.

    Device diagnostics (error flags, communication failures, firmware/version objects) are
    dropped: they are real KNX objects but not entities a user wants suggested; they land in
    ``hints["diagnostics_skipped"]`` instead."""
    skipped = skipped if skipped is not None else []
    out = []
    for l in links:
        if l.role != "source" or l.ga in sink_gas:
            continue
        m, s = l.dpt
        if m is None:
            continue
        if _has(l.text, _DIAG_WORDS) or _has(l.name, _DIAG_WORDS):
            skipped.append(l)          # device health, not a building sensor
            continue
        meta = {"tier": "structural", "evidence": ["channel", "flags:transmit-only", "dpt"], "review": []}
        if m == 1:
            out.append((["binary_sensor"], {"binary_sensor": {"ga_sensor": _ga_conf(l, "state")}}, meta, l))
        elif m in (5, 6, 7, 8, 9, 12, 13, 14, 16) and _dpt_str(project["group_addresses"][l.ga]):
            out.append((["sensor"], {"sensor": {"ga_sensor": _ga_conf(l, "state", _dpt_str(project["group_addresses"][l.ga]))}}, meta, l))
    return out


def _pseudo_channels(project: dict[str, Any], dev: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Devices whose application declares no channels (older HDL/ABB/…): group the
    device's linked objects by their vendor object text ("Group 1", "Output A"), and
    attach status objects whose text starts with that text ("Output A status")."""
    cos = project["communication_objects"]
    ids = [cid for cid in (dev.get("communication_object_ids") or []) if cid in cos] or \
          [cid for cid, co in cos.items() if co.get("device_address") == dev.get("individual_address")]
    groups: dict[str, list[str]] = defaultdict(list)
    sources: list[tuple[str, str]] = []
    for cid in ids:
        co = cos[cid]
        if not co.get("group_address_links"):
            continue
        text = (co.get("text") or co.get("name") or "").strip()
        role = _role(co)
        if role == "sink":
            groups[text].append(cid)
        elif role == "source":
            sources.append((text, cid))
    for text, cid in sources:
        owner = next((g for g in groups if g and text.lower().startswith(g.lower())), None)
        groups[owner if owner is not None else text].append(cid)
    return {f"obj:{t or i}": {"identifier": t, "name": t, "communication_object_ids": c, "functional_blocks": None}
            for i, (t, c) in enumerate(groups.items())}


def _matched(knx: dict[str, Any], gas: dict[str, Any]) -> list[dict[str, str]]:
    found: set[str] = set()

    def walk(d):
        for k, v in d.items():
            if isinstance(v, dict):
                walk(v)
            elif k in ("write", "state") and isinstance(v, str):
                found.add(v)
            elif k == "passive" and isinstance(v, list):
                found.update(v)
    walk(knx)
    return [{"address": a, "name": (gas.get(a) or {}).get("name", "")} for a in sorted(found)]


def _common_prefix_name(names: list[str]) -> str:
    words = [n.split() for n in names if n]
    if not words:
        return ""
    pref: list[str] = []
    for i, w in enumerate(words[0]):
        if all(len(x) > i and x[i].lower() == w.lower() for x in words):
            pref.append(w)
        else:
            break
    return " ".join(pref).strip(" -_:/")


# ─────────────────────────────────────────────────────────────────────────────
def suggest_entities(project: dict[str, Any], *, skip_fb_covered: bool = True,
                     fallback: bool = True) -> dict[str, Any]:
    """→ ``{"suggestions": [EntitySuggestion...], "hints": {...}}`` (HA PR #180891 shape)."""
    gas = project.get("group_addresses") or {}
    cos = project.get("communication_objects") or {}
    if not gas:
        return {"suggestions": [], "hints": {"state": "no_project"}}

    # every GA some device WRITES to (receives commands on) — a transmit-only link
    # elsewhere to such a GA is a push button, not a sensor
    sink_gas: set[str] = set()
    for co in cos.values():
        fl = co.get("flags") or {}
        if fl.get("write"):
            sink_gas.update(a for a in (co.get("group_address_links") or []) if a in gas)

    # a GA several channels REPORT on (e.g. one "anti-seize active" status for seven
    # heating channels) is not any single entity's state
    src_owner: dict[str, set[str]] = defaultdict(set)
    for cid, co in cos.items():
        if _role(co) == "source":
            for a in (co.get("group_address_links") or [])[:1]:
                src_owner[a].add(f"{co.get('device_address')}/{co.get('channel') or co.get('text')}")
    shared = {a for a, owners in src_owner.items() if len(owners) > 1}
    # GAs some OTHER object sends on (a button, a logic module, a visu): a command GA
    # nobody sends to and that has no status is most likely a lock/parameter input of
    # the device, not something a user switches — it is dropped, not suggested
    sent_gas: set[str] = set()
    for co in cos.values():
        if _role(co) in ("source", "dual"):
            sent_gas.update(a for a in (co.get("group_address_links") or []) if a in gas)

    suggestions: list[dict[str, Any]] = []
    covered: set[str] = set()          # GAs explained by a structural suggestion
    primaries: set[str] = set()        # primary GA per emitted entity (dedupe)
    stats = {"channels": 0, "skipped_fb_covered": 0, "structural": 0, "sensors": 0,
             "fallback": 0, "review": 0, "duplicates_skipped": 0, "pseudo_channels": 0, "unwired_flagged": 0, "subunits": 0, "diagnostics_skipped": 0}

    for dev_addr, dev in (project.get("devices") or {}).items():
        dev_name = dev.get("name") or dev.get("hardware_name") or dev_addr
        channels = dict(dev.get("channels") or {})
        if not channels:
            channels = _pseudo_channels(project, dev)
            stats["pseudo_channels"] += len(channels)
        for ch_id, ch in channels.items():
            stats["channels"] += 1
            links = _links_of(project, ch.get("communication_object_ids") or [], shared)
            if skip_fb_covered and any(fb in FB_COVERED for fb in (ch.get("functional_blocks") or ())):
                stats["skipped_fb_covered"] += 1
                # the FB provider owns every GA of this channel — keep the fallback off them too
                covered.update(l.ga for l in links)
                covered.update(a for l in links for a in l.passive)
                continue
            if not links:
                continue
            units = _split_subunits(links)
            if len(units) > 1:
                stats["subunits"] += len(units)
            items: list = []
            taken: set[str] = set()
            sens: list = []
            for unit_id, unit_links in units:
                res = _classify_channel(project, unit_links, ch.get("name") or "")
                if res:
                    items.append((*res, unit_id))
                    taken |= {m["address"] for m in _matched(res[1][res[0][0]], gas)}
            for unit_id, unit_links in units:
                dropped: list = []
                sens.extend(_sensor_suggestions(project, unit_links, sink_gas | taken, dropped))
                stats["diagnostics_skipped"] += len(dropped)
                # a diagnostics object stays out of the name-based fallback too, otherwise the
                # engine resurrects it one step later as a binary sensor
                covered.update(l.ga for l in dropped)
            for platforms, confs, meta, *rest in items + sens:
                lnk = rest[0] if rest and isinstance(rest[0], _Link) else None
                unit = rest[0] if rest and not isinstance(rest[0], _Link) else (
                    _subunit(lnk) if lnk else None)
                first = confs[platforms[0]]
                mg = _matched(first, gas)
                prim = next((m["address"] for m in mg if m["address"] in
                             {first.get(k, {}).get("write") or first.get(k, {}).get("state")
                              for k in ("ga_up_down", "ga_switch", "ga_temperature_current", "ga_sensor")}), None)
                if prim in primaries:
                    stats["duplicates_skipped"] += 1   # another channel writes the same GA
                    continue
                if platforms[0] in ("light", "switch", "cover"):
                    has_state = "'state'" in str(first)
                    if not has_state and prim not in sent_gas:
                        # kept (scene/visu-driven outputs exist) but flagged: could be a
                        # lock/parameter input of the device rather than a user-facing output
                        meta["review"].append("no status object and nothing on the bus sends to this GA")
                        stats["unwired_flagged"] += 1
                    if _has(ch.get("name") or "", _INPUT_WORDS):
                        meta["review"].append("channel looks like a binary INPUT, not an actuator output")
                if prim:
                    primaries.add(prim)
                name = (lnk.name if lnk else (ch.get("name") or "")) or \
                    _common_prefix_name([m["name"] for m in mg]) or dev_name
                sid = f"{dev_addr}_{ch_id}" + (f"_{unit}" if unit else "") + (f"_{lnk.ga}" if lnk else "")
                suggestions.append({
                    "id": sid, "source": PROVIDER_ID, "suggested_name": name,
                    "group_id": dev_addr, "group_name": dev_name,
                    "secondary_info": (f"{ch.get('name') or ''} [{unit}]".strip() if unit
                                       else (ch.get("name") or "")),
                    "platform_options": platforms,
                    "suggestions": {p: {"knx": c, "matched_group_addresses": _matched(c, gas),
                                        "unmatched_dpas": []} for p, c in confs.items()},
                    "existing_entity_ids": [],
                    "metadata": {**meta, "channel": ch_id},
                })
                covered.update(m["address"] for m in mg)
                stats["sensors" if lnk else "structural"] += 1
                if meta["review"]:
                    stats["review"] += 1

    if fallback:
        for s in _fallback_suggestions(project, covered):
            suggestions.append(s)
            stats["fallback"] += 1
            if s["metadata"]["review"]:
                stats["review"] += 1

    return {"suggestions": suggestions,
            "hints": {"state": "ok", **stats}}


# ─────────────────────────────────────────────────────────────────────────────
# Fallback: GAs no channel explains → name / ETS-Function pairing engine
_YAML_TO_UI = {
    "light": {"address": ("ga_switch", "write"), "state_address": ("ga_switch", "state"),
              "brightness_address": ("ga_brightness", "write"),
              "brightness_state_address": ("ga_brightness", "state"),
              "color_temperature_address": ("ga_color_temp", "write"),
              "color_temperature_state_address": ("ga_color_temp", "state")},
    "switch": {"address": ("ga_switch", "write"), "state_address": ("ga_switch", "state")},
    "cover": {"move_long_address": ("ga_up_down", "write"), "move_short_address": ("ga_step", "write"),
              "stop_address": ("ga_stop", "write"), "position_address": ("ga_position_set", "write"),
              "position_state_address": ("ga_position_state", "state"),
              "angle_address": ("ga_angle", "write"), "angle_state_address": ("ga_angle", "state")},
    "climate": {"temperature_address": ("ga_temperature_current", "state"),
                "target_temperature_address": ("target_temperature.ga_temperature_target", "write"),
                "target_temperature_state_address": ("target_temperature.ga_temperature_target", "state"),
                "operation_mode_address": ("ga_operation_mode", "write"),
                "operation_mode_state_address": ("ga_operation_mode", "state"),
                "command_value_state_address": ("ga_valve", "state")},
    "binary_sensor": {"state_address": ("ga_sensor", "state")},
    "sensor": {"state_address": ("ga_sensor", "state")},
}
_PRIMARY = {"light": ("address", "brightness_address"), "switch": ("address",),
            "cover": ("move_long_address", "position_address"), "climate": ("temperature_address",),
            "binary_sensor": ("state_address",), "sensor": ("state_address",)}


def _set_path(conf: dict[str, Any], path: str, slot: str, value: str) -> None:
    node = conf
    parts = path.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node.setdefault(parts[-1], {})[slot] = value


def _device_of(project: dict[str, Any], ga: str) -> tuple[str, str]:
    """Device that WRITES to ``ga`` (its actuator), else any device linked to it."""
    any_dev = None
    for co in project["communication_objects"].values():
        if ga in (co.get("group_address_links") or []):
            if (co.get("flags") or {}).get("write"):
                d = co.get("device_address") or ""
                dev = project["devices"].get(d) or {}
                return d, dev.get("name") or dev.get("hardware_name") or d
            any_dev = any_dev or co.get("device_address")
    if any_dev:
        dev = project["devices"].get(any_dev) or {}
        return any_dev, dev.get("name") or dev.get("hardware_name") or any_dev
    return "", ""


def _fallback_suggestions(project: dict[str, Any], covered: set[str]) -> list[dict[str, Any]]:
    loaded = build_loaded_from_raw(cast("Any", project),
                                   project.get("info", {}).get("name") or "project.knxproj")
    res = generate_ha_yaml(loaded)
    doc = yaml.safe_load(res["yaml"]) or {}
    knx = doc.get("knx") or {}
    review_by_addr: dict[str, list[str]] = defaultdict(list)
    for r in res.get("review") or []:
        if r.get("address"):
            review_by_addr[r["address"]].append(r.get("reason", "review"))
    gas = project["group_addresses"]
    out = []
    for platform, ents in knx.items():
        if platform not in _YAML_TO_UI or not isinstance(ents, list):
            continue
        for ent in ents:
            prim = next((ent.get(k) for k in _PRIMARY[platform] if ent.get(k)), None)
            if not prim or prim in covered:
                continue
            conf: dict[str, Any] = {}
            for ykey, (path, slot) in _YAML_TO_UI[platform].items():
                if ent.get(ykey):
                    _set_path(conf, path, slot, ent[ykey])
            if platform == "sensor":
                d = _dpt_str(gas.get(prim) or {})
                if not d:
                    continue
                conf["ga_sensor"]["dpt"] = d
            if platform == "light" and "ga_switch" not in conf:
                continue
            dev_addr, dev_name = _device_of(project, prim)
            mg = _matched(conf, gas)
            covered.update(m["address"] for m in mg)
            review = list(review_by_addr.get(prim, []))
            review.append("paired by names / ETS Functions, not by device channel")
            out.append({
                "id": f"ga_{prim.replace('/', '-')}", "source": PROVIDER_ID,
                "suggested_name": ent.get("name") or (gas.get(prim) or {}).get("name") or prim,
                "group_id": dev_addr or "unassigned", "group_name": dev_name or "no device",
                "secondary_info": (gas.get(prim) or {}).get("name") or "",
                "platform_options": [platform] + (["switch"] if platform == "light" and "ga_brightness" not in conf else []),
                "suggestions": {platform: {"knx": conf, "matched_group_addresses": mg, "unmatched_dpas": []},
                                **({"switch": {"knx": {"ga_switch": conf["ga_switch"]}, "matched_group_addresses": _matched({"ga_switch": conf["ga_switch"]}, gas), "unmatched_dpas": []}}
                                   if platform == "light" and "ga_brightness" not in conf else {})},
                "existing_entity_ids": [],
                "metadata": {"tier": "heuristic", "evidence": ["name", "ets_function"], "review": review},
            })
    return out
