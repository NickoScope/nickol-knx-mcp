"""Room Template Library — R1 (vertical slice).

Compose a NEW KNX project from a list of parametrised *room templates*.

Design contract (see ``room_templates/SCHEMA.md``):

  * A room template is a locale-neutral YAML file. Its identity is a semantic
    ``slot_id`` (an ASCII identifier), **never** its human name — ``labels.ru`` /
    ``labels.en`` are presentation only, so a translation never changes identity.
  * Each template declares ``parameters`` (window count, lighting-circuit count,
    …). ``area_m2`` is a **hint** that seeds defaults, carrying provenance; it is
    never treated as a normative fact and, in R1, never changes GA counts.
  * Each template declares functional **slots**. A slot carries per-slot
    ``basic`` / ``comfort`` presets (NOT one monolithic room level), so a house
    can mix "comfort climate + basic lighting" per room.
  * Slots reference **function types** (lighting_switch, lighting_dimmer,
    shutter, climate_floor, presence). A function type expands into a fixed set
    of KNX communication objects (command + status), each with a canonical DPT.

The composition pipeline is deliberately layered and pure:

    templates + room specs
        -> resolved functional model (IR dataclasses; NOT ``GARecord``)
        -> address allocation (main = domain, middle = role, sub sequential)
        -> a real ``.knxproj`` ZIP (ETS project/22 XML)
        -> re-read through :func:`project.load_project` (the SAME reader used for
           third-party projects) so the generator never touches the classifier.

Everything downstream (ETS export, linters, manifest, BOM) runs off the re-read
project, exactly like a hand-made ETS file. The server never writes to a bus.

R1 scope: NEW projects only, dry-run by default. Docking into an existing
project (allocation lockfile, drift detection) and the exact device-resolver are
R2 — see ``docs/roadmap/room-library/implementation-plan.md``.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from dataclasses import dataclass, field
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# Public format contract
# --------------------------------------------------------------------------- #
SCHEMA_VERSION = 1
SUPPORTED_LANGUAGES = ("ru", "en")

# Default 3-level taxonomy (CLAUDE.md methodology — main group = function domain).
DOMAIN_MAIN: dict[str, int] = {
    "central": 0,
    "lighting": 1,
    "shutter": 2,
    "hvac": 3,
    "sensor": 4,
    "energy": 5,
    "diagnostics": 6,
    "reserve": 7,
}

DOMAIN_LABELS: dict[str, dict[str, str]] = {
    "central": {"ru": "Центральные функции", "en": "Central"},
    "lighting": {"ru": "Освещение", "en": "Lighting"},
    "shutter": {"ru": "Шторы", "en": "Shutters"},
    "hvac": {"ru": "Климат", "en": "HVAC"},
    "sensor": {"ru": "Датчики", "en": "Sensors"},
    "energy": {"ru": "Энергия", "en": "Energy"},
    "diagnostics": {"ru": "Диагностика", "en": "Diagnostics"},
    "reserve": {"ru": "Резерв", "en": "Reserve"},
}

# Middle group = role/sub-function inside a domain. Command roles and their
# feedback roles live in DISTINCT, predictable middles (the pairing engine keys
# off name tokens, not adjacency — see CLAUDE.md).
MIDDLE_ROLE: dict[str, dict[str, int]] = {
    "lighting": {"cmd_onoff": 0, "dimming": 1, "brightness_value": 2,
                 "status_onoff": 3, "brightness_status": 4},
    "shutter": {"move": 0, "stop": 1, "position": 2, "slat": 3,
                "position_status": 4},
    "hvac": {"onoff": 0, "mode": 1, "setpoint": 2, "fan": 3, "status": 4,
             "actual_temp": 5},
    "sensor": {"presence": 0, "illuminance": 1, "climate": 2},
    "central": {"scene": 0, "command": 1},
}

MIDDLE_LABELS: dict[str, dict[int, dict[str, str]]] = {
    "lighting": {0: {"ru": "Вкл/Выкл", "en": "On/Off"},
                 1: {"ru": "Диммирование", "en": "Dimming"},
                 2: {"ru": "Значение яркости", "en": "Brightness value"},
                 3: {"ru": "Статус вкл/выкл", "en": "On/Off status"},
                 4: {"ru": "Статус яркости", "en": "Brightness status"}},
    "shutter": {0: {"ru": "Движение", "en": "Move"},
                1: {"ru": "Стоп", "en": "Stop"},
                2: {"ru": "Позиция", "en": "Position"},
                3: {"ru": "Ламели", "en": "Slats"},
                4: {"ru": "Статус позиции", "en": "Position status"}},
    "hvac": {0: {"ru": "Вкл/Выкл", "en": "On/Off"},
             1: {"ru": "Режим", "en": "Mode"},
             2: {"ru": "Уставка", "en": "Setpoint"},
             3: {"ru": "Вентилятор", "en": "Fan"},
             4: {"ru": "Статусы", "en": "Statuses"},
             5: {"ru": "Температура факт", "en": "Actual temperature"}},
    "sensor": {0: {"ru": "Присутствие/Движение", "en": "Presence/Motion"},
               1: {"ru": "Освещённость", "en": "Illuminance"},
               2: {"ru": "Климат в комнатах", "en": "Room climate"}},
    "central": {0: {"ru": "Сцены", "en": "Scenes"},
                1: {"ru": "Центральные команды", "en": "Central commands"}},
}

MAX_SUB = 255          # 3-level sub range 0..255; sub 0 reserved as range anchor
MAX_MIDDLE = 7         # 3-level middle range 0..7


# --------------------------------------------------------------------------- #
# Function-type object model (function-first: objects, not devices).
# Each object: role_key, ru label, en label, dpt (main, sub), kind, domain,
# middle_role. Command objects are paired to their status object by name tokens.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ObjSpec:
    role: str
    label_ru: str
    label_en: str
    dpt_main: int
    dpt_sub: int
    kind: str        # command | status | sensor
    domain: str
    middle_role: str

    def label(self, language: str) -> str:
        return self.label_ru if language == "ru" else self.label_en

    @property
    def dpst(self) -> str:
        return f"DPST-{self.dpt_main}-{self.dpt_sub}"


FUNCTION_OBJECTS: dict[str, list[ObjSpec]] = {
    "lighting_switch": [
        ObjSpec("onoff", "вкл/выкл", "on/off", 1, 1, "command", "lighting", "cmd_onoff"),
        ObjSpec("onoff_status", "статус", "status", 1, 11, "status", "lighting", "status_onoff"),
    ],
    "lighting_dimmer": [
        ObjSpec("onoff", "вкл/выкл", "on/off", 1, 1, "command", "lighting", "cmd_onoff"),
        ObjSpec("dimming", "диммирование", "dimming", 3, 7, "command", "lighting", "dimming"),
        ObjSpec("brightness", "яркость", "brightness", 5, 1, "command", "lighting", "brightness_value"),
        ObjSpec("onoff_status", "статус", "status", 1, 11, "status", "lighting", "status_onoff"),
        ObjSpec("brightness_status", "яркость статус", "brightness status", 5, 1, "status", "lighting", "brightness_status"),
    ],
    "shutter": [
        ObjSpec("updown", "вверх/вниз", "up/down", 1, 8, "command", "shutter", "move"),
        ObjSpec("stop", "стоп", "stop", 1, 10, "command", "shutter", "stop"),
        ObjSpec("position", "позиция", "position", 5, 1, "command", "shutter", "position"),
        ObjSpec("position_status", "позиция статус", "position status", 5, 1, "status", "shutter", "position_status"),
    ],
    "climate_floor": [
        ObjSpec("onoff", "вкл/выкл", "on/off", 1, 1, "command", "hvac", "onoff"),
        ObjSpec("setpoint", "уставка", "setpoint", 9, 1, "command", "hvac", "setpoint"),
        ObjSpec("mode", "режим", "mode", 20, 102, "command", "hvac", "mode"),
        ObjSpec("onoff_status", "статус", "status", 1, 11, "status", "hvac", "status"),
        ObjSpec("setpoint_status", "уставка статус", "setpoint status", 9, 1, "status", "hvac", "status"),
        ObjSpec("mode_status", "режим статус", "mode status", 20, 102, "status", "hvac", "status"),
        ObjSpec("actual_temp", "температура факт", "actual temperature", 9, 1, "sensor", "hvac", "actual_temp"),
    ],
    "presence": [
        ObjSpec("occupancy", "присутствие", "occupancy", 1, 18, "sensor", "sensor", "presence"),
        ObjSpec("illuminance", "освещённость", "illuminance", 9, 4, "sensor", "sensor", "illuminance"),
    ],
}

# Function type -> candidate device recipe (device_library) for the BOM proposal.
BOM_RECIPE: dict[str, str] = {
    "lighting_switch": "switch_output",
    "lighting_dimmer": "dimmer_channel",
    "shutter": "shutter_channel",
    "climate_floor": "floor_heating_zone",
    "presence": "presence_detector",
}


class RoomLibraryError(ValueError):
    """Raised on an unrecoverable composition error (address exhaustion, bad
    template, colliding room labels). Never a silent overflow."""


# --------------------------------------------------------------------------- #
# Resolved intermediate model (IR) — deliberately separate dataclasses, NOT the
# public GARecord. The IR is the composition's own contract; GARecord only
# appears AFTER the generated project is re-read by the standard loader.
# --------------------------------------------------------------------------- #
@dataclass
class ResolvedObject:
    role: str
    name: str
    dpt_main: int
    dpt_sub: int
    kind: str
    domain: str
    main: int
    middle: int
    sub: int

    @property
    def address(self) -> str:
        return f"{self.main}/{self.middle}/{self.sub}"

    @property
    def dpst(self) -> str:
        return f"DPST-{self.dpt_main}-{self.dpt_sub}"


@dataclass
class ResolvedSlot:
    slot_id: str
    label: str
    function_type: str
    index: int          # 1-based index within a multi-instance slot
    objects: list[ResolvedObject] = field(default_factory=list)


@dataclass
class ResolvedRoom:
    template_id: str
    label: str
    preset: str
    params: dict[str, Any]
    slots: list[ResolvedSlot] = field(default_factory=list)


@dataclass
class ComposedHouse:
    project_name: str
    language: str
    rooms: list[ResolvedRoom] = field(default_factory=list)

    @property
    def objects(self) -> list[ResolvedObject]:
        out: list[ResolvedObject] = []
        for r in self.rooms:
            for s in r.slots:
                out.extend(s.objects)
        return out


# --------------------------------------------------------------------------- #
# Template loading
# --------------------------------------------------------------------------- #
def _templates_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "room_templates")


def load_builtin_templates() -> dict[str, dict[str, Any]]:
    """Load every built-in room template keyed by its semantic ``slot_id``."""
    import yaml
    out: dict[str, dict[str, Any]] = {}
    d = _templates_dir()
    for fn in sorted(os.listdir(d)):
        if not fn.endswith((".yaml", ".yml")):
            continue
        with open(os.path.join(d, fn), encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict) and data.get("slot_id"):
            data.setdefault("_source_file", fn)
            out[data["slot_id"]] = data
    return out


def load_template_file(path: str) -> dict[str, Any]:
    import yaml
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise RoomLibraryError(f"{path}: template root must be a mapping")
    data.setdefault("_source_file", os.path.basename(path))
    return data


# --------------------------------------------------------------------------- #
# Template validation (schema-valid rung of the validity ladder)
# --------------------------------------------------------------------------- #
_IDENT_OK = set("abcdefghijklmnopqrstuvwxyz0123456789_")


def _is_ident(s: Any) -> bool:
    return isinstance(s, str) and bool(s) and set(s) <= _IDENT_OK


def _finding(severity: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
    f = {"severity": severity, "code": code, "message": message}
    f.update(extra)
    return f


def validate_template(tmpl: dict[str, Any]) -> dict[str, Any]:
    """Validate one room template against the R1 schema. Report-only.

    Returns ``{ok, schema_version, slot_id, findings}``. ``ok`` is False when any
    finding is an error.
    """
    findings: list[dict[str, Any]] = []

    sv = tmpl.get("schema_version")
    if sv is None:
        findings.append(_finding("error", "schema_version_missing",
                                 "Template has no schema_version (breaks migration/compat)."))
    elif sv != SCHEMA_VERSION:
        findings.append(_finding("error", "schema_version_unsupported",
                                 f"schema_version {sv} is not supported (this build understands "
                                 f"{SCHEMA_VERSION})."))

    slot_id = tmpl.get("slot_id")
    if not _is_ident(slot_id):
        findings.append(_finding("error", "slot_id_invalid",
                                 "Template slot_id must be a locale-neutral ASCII identifier "
                                 "(identity must not come from a human name)."))

    labels = tmpl.get("labels") or {}
    for lang in SUPPORTED_LANGUAGES:
        if not (labels.get(lang) or "").strip():
            findings.append(_finding("error", "label_missing",
                                     f"Template is missing labels.{lang}.", lang=lang))

    # parameters: each needs a default; area_m2 must be declared a hint with provenance.
    params = tmpl.get("parameters") or {}
    if not isinstance(params, dict):
        findings.append(_finding("error", "parameters_invalid", "parameters must be a mapping."))
        params = {}
    for pname, pdef in params.items():
        if not isinstance(pdef, dict) or "default" not in pdef:
            findings.append(_finding("error", "parameter_no_default",
                                     f"Parameter '{pname}' has no default.", parameter=pname))
            continue
        if pname == "area_m2":
            if pdef.get("role") != "hint":
                findings.append(_finding("error", "area_not_hint",
                                         "area_m2 must be declared role: hint — area is a defaults "
                                         "recommender, never a normative fact.", parameter=pname))
            if not pdef.get("provenance"):
                findings.append(_finding("warning", "area_no_provenance",
                                         "area_m2 should carry provenance (source/user_overridden).",
                                         parameter=pname))

    # slots
    slots = tmpl.get("slots") or []
    if not isinstance(slots, list) or not slots:
        findings.append(_finding("error", "slots_missing", "Template declares no slots."))
        slots = []
    seen_slots: set[str] = set()
    for i, slot in enumerate(slots):
        if not isinstance(slot, dict):
            findings.append(_finding("error", "slot_invalid", f"Slot #{i} is not a mapping."))
            continue
        sid = slot.get("slot_id")
        if not _is_ident(sid):
            findings.append(_finding("error", "slot_id_invalid",
                                     f"Slot #{i} slot_id must be a locale-neutral identifier.",
                                     slot=sid))
        elif sid in seen_slots:
            findings.append(_finding("error", "slot_id_duplicate",
                                     f"Slot id '{sid}' is used more than once.", slot=sid))
        else:
            seen_slots.add(sid)
        slabels = slot.get("labels") or {}
        for lang in SUPPORTED_LANGUAGES:
            if not (slabels.get(lang) or "").strip():
                findings.append(_finding("error", "slot_label_missing",
                                         f"Slot '{sid}' is missing labels.{lang}.",
                                         slot=sid, lang=lang))
        presets = slot.get("presets") or {}
        if not isinstance(presets, dict) or not {"basic", "comfort"} <= set(presets):
            findings.append(_finding("error", "slot_presets_missing",
                                     f"Slot '{sid}' must define both basic and comfort presets.",
                                     slot=sid))
            presets = presets if isinstance(presets, dict) else {}
        for pname, pdef in presets.items():
            if not isinstance(pdef, dict):
                findings.append(_finding("error", "preset_invalid",
                                         f"Slot '{sid}' preset '{pname}' must be a mapping.",
                                         slot=sid, preset=pname))
                continue
            if not pdef.get("enabled", False):
                continue  # a disabled preset needs no function/multiplicity
            ftype = pdef.get("function")
            if ftype not in FUNCTION_OBJECTS:
                findings.append(_finding("error", "unknown_function",
                                         f"Slot '{sid}' preset '{pname}' uses unknown function "
                                         f"'{ftype}'. Known: {sorted(FUNCTION_OBJECTS)}.",
                                         slot=sid, preset=pname, function=ftype))
            mult = pdef.get("multiplicity") or {}
            if not _mult_is_valid(mult, params):
                findings.append(_finding("error", "multiplicity_invalid",
                                         f"Slot '{sid}' preset '{pname}' multiplicity {mult} is "
                                         "invalid (need {fixed: N} or {param: <declared param>}).",
                                         slot=sid, preset=pname))

    errors = sum(1 for f in findings if f["severity"] == "error")
    return {
        "ok": errors == 0,
        "schema_version": sv,
        "slot_id": slot_id,
        "source_file": tmpl.get("_source_file"),
        "findings_summary": {"errors": errors,
                             "warnings": sum(1 for f in findings if f["severity"] == "warning"),
                             "total": len(findings)},
        "findings": findings,
    }


# Public alias (the MCP tool name mirrors this).
validate_room_template = validate_template


def _mult_is_valid(mult: Any, params: dict[str, Any]) -> bool:
    if not isinstance(mult, dict):
        return False
    if "fixed" in mult:
        return isinstance(mult["fixed"], int) and mult["fixed"] >= 0
    if "param" in mult:
        return mult["param"] in params
    return False


# --------------------------------------------------------------------------- #
# Resolution: templates + room specs -> ResolvedRoom (function-first IR)
# --------------------------------------------------------------------------- #
def _canonical_key(spec: dict[str, Any]) -> str:
    """Order-independent identity of a room request, so permuting the room list
    yields byte-identical output (permutation invariance)."""
    return json.dumps({
        "template": spec.get("template"),
        "preset": spec.get("preset", "basic"),
        "params": spec.get("params") or {},
        "slot_presets": spec.get("slot_presets") or {},
        "label": spec.get("label"),
    }, sort_keys=True, ensure_ascii=False)


def _resolve_multiplicity(mult: dict[str, Any], params: dict[str, Any]) -> int:
    if "fixed" in mult:
        return max(0, int(mult["fixed"]))
    if "param" in mult:
        return max(0, int(params.get(mult["param"], 0)))
    return 0


def _room_params(tmpl: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for pname, pdef in (tmpl.get("parameters") or {}).items():
        params[pname] = pdef.get("default")
    for pname, val in (override or {}).items():
        params[pname] = val
    return params


def _instance_labels(rooms: list[dict[str, Any]], templates: dict[str, dict[str, Any]],
                     language: str) -> list[str]:
    """Assign a unique, human-readable zone label to each (canonically sorted)
    room. Same template used N times -> base label, base 2, base 3 …"""
    labels: list[str] = []
    counts: dict[str, int] = {}
    for spec in rooms:
        tmpl = templates[spec["template"]]
        base = spec.get("label") or (tmpl.get("labels") or {}).get(language) or spec["template"]
        counts[base] = counts.get(base, 0) + 1
        labels.append(base if counts[base] == 1 else f"{base} {counts[base]}")
    return labels


def resolve_house(rooms: list[dict[str, Any]], templates: dict[str, dict[str, Any]],
                  language: str = "ru", project_name: str = "Room Library house") -> ComposedHouse:
    """Resolve room specs into an allocated :class:`ComposedHouse`.

    Deterministic and permutation-invariant: rooms are sorted by a canonical key
    before allocation, so the same *set* of rooms always yields identical
    addresses regardless of input order.
    """
    if language not in SUPPORTED_LANGUAGES:
        raise RoomLibraryError(f"language must be one of {SUPPORTED_LANGUAGES}")
    if not rooms:
        raise RoomLibraryError("compose needs at least one room")

    # composition-valid rung: every referenced template must exist & validate.
    for spec in rooms:
        tid = spec.get("template")
        if tid not in templates:
            raise RoomLibraryError(f"unknown template '{tid}'. Known: {sorted(templates)}")
        v = validate_template(templates[tid])
        if not v["ok"]:
            raise RoomLibraryError(f"template '{tid}' is invalid: {v['findings']}")

    ordered = sorted(rooms, key=_canonical_key)
    labels = _instance_labels(ordered, templates, language)
    if len(set(labels)) != len(labels):
        raise RoomLibraryError(f"room labels collide: {labels} — give distinct 'label' overrides")

    # sub counter per (main, middle); sub 0 is the range anchor, GAs start at 1.
    sub_counter: dict[tuple[int, int], int] = {}

    def alloc(domain: str, middle_role: str) -> tuple[int, int, int]:
        main = DOMAIN_MAIN[domain]
        middle = MIDDLE_ROLE[domain][middle_role]
        if middle > MAX_MIDDLE:
            raise RoomLibraryError(
                f"middle group {middle} out of range for domain '{domain}'")
        key = (main, middle)
        nxt = sub_counter.get(key, 0) + 1
        if nxt > MAX_SUB:
            raise RoomLibraryError(
                f"address space exhausted in {main}/{middle}/* (>{MAX_SUB} sub-addresses); "
                "split the domain across more middle groups or projects — refusing to overflow")
        sub_counter[key] = nxt
        return main, middle, nxt

    house = ComposedHouse(project_name=project_name, language=language)
    for spec, zone_label in zip(ordered, labels):
        tmpl = templates[spec["template"]]
        room_preset = spec.get("preset", "basic")
        slot_presets = spec.get("slot_presets") or {}
        params = _room_params(tmpl, spec.get("params") or {})
        room = ResolvedRoom(template_id=spec["template"], label=zone_label,
                            preset=room_preset, params=params)

        for slot in tmpl.get("slots") or []:
            sid = slot["slot_id"]
            eff_preset = slot_presets.get(sid, room_preset)
            pdef = (slot.get("presets") or {}).get(eff_preset) or {}
            if not pdef.get("enabled", False):
                continue
            ftype = pdef["function"]
            n = _resolve_multiplicity(pdef.get("multiplicity") or {}, params)
            slot_label = (slot.get("labels") or {}).get(language, sid)
            for idx in range(1, n + 1):
                inst_label = slot_label if n == 1 else f"{slot_label} {idx}"
                rslot = ResolvedSlot(slot_id=sid, label=inst_label,
                                     function_type=ftype, index=idx)
                for obj in FUNCTION_OBJECTS[ftype]:
                    main, middle, sub = alloc(obj.domain, obj.middle_role)
                    name = f"{zone_label} {inst_label} {obj.label(language)}"
                    rslot.objects.append(ResolvedObject(
                        role=obj.role, name=name,
                        dpt_main=obj.dpt_main, dpt_sub=obj.dpt_sub,
                        kind=obj.kind, domain=obj.domain,
                        main=main, middle=middle, sub=sub))
                room.slots.append(rslot)
        house.rooms.append(room)
    return house


# --------------------------------------------------------------------------- #
# .knxproj ZIP writer (ETS project/22). We generate a real archive and re-read
# it with the standard loader; the generator never builds GARecord directly.
# --------------------------------------------------------------------------- #
_XML_ESCAPE = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def _esc(s: str) -> str:
    return "".join(_XML_ESCAPE.get(c, c) for c in str(s))


def _master_xml() -> str:
    """knx_master.xml — copied from the shipped demo project when available,
    otherwise a minimal stub (xknxproject only needs MediumType MT-0 resolvable)."""
    for cand in (
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "examples", "demo-home", "demo-home.knxproj"),
    ):
        cand = os.path.normpath(cand)
        if os.path.isfile(cand):
            try:
                with zipfile.ZipFile(cand) as z:
                    return z.read("knx_master.xml").decode("utf-8")
            except Exception:  # noqa: BLE001
                pass
    # minimal fallback master
    return ('﻿<?xml version="1.0" encoding="utf-8"?>\n'
            '<KNX xmlns="http://knx.org/xml/project/22">\n'
            '  <MasterData>\n'
            '    <MediumTypes><MediumType Id="MT-0" Name="TP" Number="0" /></MediumTypes>\n'
            '  </MasterData>\n</KNX>\n')


def build_knxproj_bytes(house: ComposedHouse, proj_id: str = "P-ROOMLIB") -> bytes:
    """Serialise a :class:`ComposedHouse` to a real ``.knxproj`` ZIP (bytes)."""
    objs = house.objects
    # group by main -> middle for GroupRanges
    by_main: dict[int, dict[int, list[ResolvedObject]]] = {}
    domain_by_main: dict[int, str] = {}
    for o in objs:
        by_main.setdefault(o.main, {}).setdefault(o.middle, []).append(o)
        domain_by_main[o.main] = o.domain

    out: list[str] = []
    w = out.append
    w('﻿<?xml version="1.0" encoding="utf-8"?>')
    w('<KNX xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
      'xmlns:xsd="http://www.w3.org/2001/XMLSchema" CreatedBy="nickol-knx-mcp" '
      'ToolVersion="0.0.0" xmlns="http://knx.org/xml/project/22">')
    w(f'  <Project Id="{proj_id}">')
    w('    <Installations>')
    w(f'      <Installation Name="" DefaultLine="{proj_id}-0_L-1">')
    w('        <Topology>')
    w(f'          <Area Id="{proj_id}-0_A-1" Address="1" Puid="1">')
    w(f'            <Line Id="{proj_id}-0_L-1" Address="1" Puid="2">'
      f'<Segment Id="{proj_id}-0_S-1" Number="0" MediumTypeRefId="MT-0" Puid="3" /></Line>')
    w('          </Area>')
    w('        </Topology>')
    w('        <GroupAddresses>')
    w('          <GroupRanges>')
    for main in sorted(by_main):
        domain = domain_by_main[main]
        mname = DOMAIN_LABELS.get(domain, {}).get(house.language, domain)
        rs, re_ = main << 11, (main << 11) + 2047
        w(f'            <GroupRange Id="{proj_id}-0_GR-{main}" RangeStart="{rs}" '
          f'RangeEnd="{re_}" Name="{_esc(mname)}" Puid="{100 + main}">')
        for middle in sorted(by_main[main]):
            midlabel = MIDDLE_LABELS.get(domain, {}).get(middle, {}).get(
                house.language, f"Middle {middle}")
            ms, me = (main << 11) | (middle << 8), ((main << 11) | (middle << 8)) + 255
            w(f'              <GroupRange Id="{proj_id}-0_GR-{main}_{middle}" '
              f'RangeStart="{ms}" RangeEnd="{me}" Name="{_esc(midlabel)}" '
              f'Puid="{1000 + main * 8 + middle}">')
            for o in sorted(by_main[main][middle], key=lambda x: x.sub):
                raw = (o.main << 11) | (o.middle << 8) | o.sub
                w(f'                <GroupAddress Id="{proj_id}-0_GA-{raw}" Address="{raw}" '
                  f'Name="{_esc(o.name)}" DatapointType="{o.dpst}" Puid="{10000 + raw}" />')
            w('              </GroupRange>')
        w('          </GroupRange>')
    w('          </GroupRanges>')
    w('        </GroupAddresses>')
    w('      </Installation>')
    w('    </Installations>')
    w('  </Project>')
    w('</KNX>')
    zero_xml = "\n".join(out)

    project_xml = (
        '﻿<?xml version="1.0" encoding="utf-8"?>\n'
        '<KNX xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" CreatedBy="nickol-knx-mcp" '
        'ToolVersion="0.0.0" xmlns="http://knx.org/xml/project/22">\n'
        f'  <Project Id="{proj_id}">\n'
        f'    <ProjectInformation Name="{_esc(house.project_name)}" '
        'GroupAddressStyle="ThreeLevel" '
        'Comment="Generated by nickol-knx-mcp Room Library (R1) — review before ETS import" '
        'ProjectType="House" />\n'
        '  </Project>\n'
        '</KNX>\n')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{proj_id}/project.xml", project_xml)
        z.writestr(f"{proj_id}/0.xml", zero_xml)
        z.writestr("knx_master.xml", _master_xml())
        z.writestr(f"{proj_id}.signature", "nickol-knx-mcp room-library synthetic (unsigned)")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Manifest + BOM
# --------------------------------------------------------------------------- #
def build_manifest(house: ComposedHouse) -> dict[str, Any]:
    """Deterministic allocation manifest (the negative-oracle surface)."""
    rooms_out: list[dict[str, Any]] = []
    total_ga = 0
    for room in house.rooms:
        slots_out: list[dict[str, Any]] = []
        for slot in room.slots:
            slots_out.append({
                "slot_id": slot.slot_id,
                "label": slot.label,
                "function": slot.function_type,
                "index": slot.index,
                "objects": [{"role": o.role, "address": o.address, "name": o.name,
                             "dpt": f"{o.dpt_main}.{o.dpt_sub:03d}", "kind": o.kind,
                             "domain": o.domain} for o in slot.objects],
            })
            total_ga += len(slot.objects)
        rooms_out.append({
            "template": room.template_id,
            "label": room.label,
            "preset": room.preset,
            "params": room.params,
            "slots": slots_out,
        })
    # per-domain / per-main usage
    usage: dict[str, dict[str, Any]] = {}
    for o in house.objects:
        key = f"{o.main} {o.domain}"
        u = usage.setdefault(key, {"main": o.main, "domain": o.domain, "count": 0,
                                   "max_sub_used": 0})
        u["count"] += 1
        u["max_sub_used"] = max(u["max_sub_used"], o.sub)
    return {
        "schema_version": SCHEMA_VERSION,
        "project_name": house.project_name,
        "language": house.language,
        "taxonomy": {str(v): k for k, v in DOMAIN_MAIN.items()},
        "totals": {"rooms": len(house.rooms), "group_addresses": total_ga},
        "allocation": sorted(usage.values(), key=lambda x: x["main"]),
        "rooms": rooms_out,
    }


def build_bom_proposal(house: ComposedHouse) -> dict[str, Any]:
    """Propose candidate devices from the device library for the resolved
    functions. A PROPOSAL, not an exact BOM — exact set-cover selection is R2."""
    from .device_library import decompose_device
    # count function-type instances (each ResolvedSlot is one channel/zone/unit)
    counts: dict[str, int] = {}
    for room in house.rooms:
        for slot in room.slots:
            counts[slot.function_type] = counts.get(slot.function_type, 0) + 1

    items: list[dict[str, Any]] = []
    for ftype, n in sorted(counts.items()):
        recipe = BOM_RECIPE.get(ftype)
        dev = decompose_device(recipe, channels=n) if recipe else {"matched": False}
        items.append({
            "function": ftype,
            "channels_required": n,
            "candidate_recipe": recipe,
            "unit": dev.get("unit"),
            "objects_per_unit": dev.get("objects_per_unit"),
            "recipe_note": dev.get("note"),
        })
    return {
        "note": "Candidate devices only (function-first). Exact device selection with "
                "channel/price optimisation is R2; verify channel counts against real "
                "product datasheets before ordering.",
        "items": items,
    }


# --------------------------------------------------------------------------- #
# Top-level compose
# --------------------------------------------------------------------------- #
def compose(rooms: list[dict[str, Any]], language: str = "ru",
            project_name: str = "Room Library house",
            templates: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    """Compose a NEW house from room specs and return all artifacts + linter run.

    ``rooms`` items: ``{template, preset?, slot_presets?, params?, label?}``.
    Returns a dict with: manifest, ets_xml, ets_csv, bom, lint (round-trip through
    the standard loader), and the raw ``.knxproj`` bytes are NOT returned (the
    server persists them on request).
    """
    from .project import load_project
    from .analyze import validate_naming, detect_missing_status, detect_dpt_issues
    from .policy import check_policy, load_policy

    templates = templates if templates is not None else load_builtin_templates()
    house = resolve_house(rooms, templates, language=language, project_name=project_name)
    knxproj = build_knxproj_bytes(house)

    # Round-trip: write to a temp file and re-read with the SAME loader used for
    # third-party projects, then lint the re-read model (not the IR).
    import tempfile
    tf = tempfile.NamedTemporaryFile(suffix=".knxproj", delete=False)
    try:
        tf.write(knxproj)
        tf.close()
        loaded = load_project(tf.name)
    finally:
        os.unlink(tf.name)

    from .generate_ets import generate_ets_xml, generate_ets_csv
    naming = validate_naming(loaded)
    missing = detect_missing_status(loaded)
    dpt = detect_dpt_issues(loaded)
    policy = check_policy(loaded, load_policy(None))
    all_findings = naming + missing + dpt + policy.get("findings", [])
    errors = sum(1 for f in all_findings if f.get("severity") == "error")
    warnings = sum(1 for f in all_findings if f.get("severity") == "warning")

    manifest = build_manifest(house)
    return {
        "project_name": project_name,
        "language": language,
        "totals": manifest["totals"],
        "lint": {
            "reread_group_addresses": len(loaded.gas),
            "errors": errors,
            "warnings": warnings,
            "clean": errors == 0 and warnings == 0,
            "naming": naming,
            "missing_status": missing,
            "dpt": dpt,
            "policy": {"summary": policy.get("findings_summary"),
                       "findings": policy.get("findings")},
        },
        "manifest": manifest,
        "bom": build_bom_proposal(house),
        "ets_xml": generate_ets_xml(loaded),
        "ets_csv": generate_ets_csv(loaded),
        "_knxproj_bytes": knxproj,
    }
