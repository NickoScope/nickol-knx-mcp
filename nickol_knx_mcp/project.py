"""Load and parse a .knxproj file and build an enriched in-memory model.

This module is the ONLY place that touches the ETS project file. It is strictly
read-only: it opens the .knxproj archive, never modifies it, and never opens any
KNX/IP connection. The custom MCP server has no bus connectivity by design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from xknxproject import XKNXProj
from xknxproject.models import KNXProject

from .dpt_map import classify_dpt, dpt_key, is_exact_dpt, CATEGORY_UNKNOWN
from .intent import classify_intent, INTENT_FUNCTIONAL
from .safexml import preflight_archive

CATEGORY_UNKNOWN_STR = CATEGORY_UNKNOWN


# Multilingual keyword sets (EN / DE / RU) used by the heuristic fallbacks.
STATUS_KEYWORDS = [
    "status", "state", "stat", "fb", "feedback", "rueck", "rück", "rm ",
    "rm_", "статус", "состоян", "обратн", "сост.",
]
COMMAND_KEYWORDS = [
    "switch", "schalt", "dimm", "control", "steuer", "befehl", "set",
    "soll", "вкл", "выкл", "упр", "команд", "задан",
]

# Domain terms by name (used to decide a GA's functional domain as ONE signal,
# combined with the DPT and the group-range context — see _classify_category).
# Checked in this priority order (most specific first; lighting is the generic
# last resort). Matching is by WORD BOUNDARY, not bare substring, so short tokens
# like "ac" don't fire inside "terrace" and "led" doesn't fire inside "ledge".
_DOMAIN_TERMS: dict[str, list[str]] = {
    "diagnostics": ["alarm", "fault", "error", "diag", "leak", "smoke",
                    "online", "offline", "heartbeat", "watchdog",
                    "тревог", "ошибк", "диагност", "утечк", "дым", "авари", "неисправ",
                    "связь"],
    "energy": ["energy", "power", "consum", "meter", "kwh", "watt", "энерг",
               "мощност", "потребл", "счётчик", "счетчик", "тариф"],
    "scene": ["scene", "preset", "mood", "сцен", "пресет"],
    "shutter": ["blind", "shutter", "jalousie", "roll", "rollo", "marqui",
                "awning", "curtain", "behang", "lamelle", "raffstore", "markise",
                "auf/ab", "ab/auf", "штор", "жалюзи", "рольставн", "ролет", "ролл",
                "позиц", "вверх/вниз", "ламел", "position", "shade"],
    # sensor BEFORE hvac: a name with an explicit sensor word (weather station,
    # датчик, motion) is a sensor even when it measures temperature — otherwise
    # "Метеостанция - Температура" lands in hvac via the "температур" term.
    "sensor": ["sensor", "motion", "presence", "occupancy", "brightness sens", "lux",
               "humidity", "weather", "meteo", "illuminance", "датчик", "движени",
               "присутств", "влажн", "люкс", "метео", "погод",
               "освещённост", "освещенност"],  # illuminance ≠ "освещение" (checked first)
    "hvac": ["hvac", "climate", "thermostat", "heat", "cool", "ac", "a/c", "aircon",
             "air con", "air-con", "conditioner", "ventilation", "radiator", "boiler",
             "underfloor", "fancoil", "fan coil", "fan-coil", "fan", "valve", "setpoint",
             "климат", "отопл", "тёпл", "тепл", "конвектор", "вентил",
             "клапан", "кондиц", "котёл", "радиатор", "фанкойл", "уставк",
             "а/с", "сплит", "вытяжк"],
    # NOTE: no bare "температур"/"temperature" term — a temperature GA takes its
    # domain from context (уставк/кондиц/тёпл name words, or its main group):
    # "Гостиная температура" in a Sensors main is a sensor, not an HVAC actuator.
    "lighting": ["light", "lamp", "dimm", "led", "spot", "sconce", "chandelier",
                 "rgb", "rgbw", "colour", "color", "xyy",
                 "свет", "лампа", "подсветк", "освещ", "люстра", "диммер", "бра", "торшер",
                 "яркост"],  # RU only: EN "brightness" also means weather lux — too ambiguous
}

# Domains a group-range name may legitimately pin for an actuator command whose
# DPT is domain-soft: a switch/scaling in a "Lighting"/"Shutters"/"HVAC" range is
# that load. A range named "Scenes"/"Sensors"/"Energy" does NOT retype a 1-bit
# command into a scene/sensor/energy datapoint — those carry their own strong DPTs.
_RANGE_ASSIGNABLE = {"lighting", "shutter", "hvac"}

# Short/ambiguous tokens need a boundary on BOTH sides (whole word), else they
# fire inside unrelated words ("ac" in "terrace", "led" in "ledge"). "а/с" is the
# Cyrillic air-con abbreviation. "spot" is NOT here: prefix-matching lets "spots"
# hit, and no KNX name plausibly embeds it mid-word.
_AMBIGUOUS_TERMS = {"ac", "a/c", "а/с", "led", "fan", "co2", "uv", "rgb", "lux", "roll"}


def _compile_domain(terms: list[str]) -> "re.Pattern":
    parts = []
    for t in terms:
        esc = re.escape(t)
        parts.append(rf"\b{esc}\b" if (t in _AMBIGUOUS_TERMS or len(t) <= 2) else rf"\b{esc}")
    return re.compile("|".join(parts))


_DOMAIN_RE = {dom: _compile_domain(terms) for dom, terms in _DOMAIN_TERMS.items()}


# Location phrases that CONTAIN a domain word but describe WHERE, not WHAT:
# "Boiler room light" is a light in the boiler room, not an HVAC function.
_LOCATION_STOP_RE = re.compile(r"\b(boiler\s*room|котельн\w*|laundry\s*room)\b")


def _domain_from_text(text: str) -> Optional[str]:
    """Return the functional domain a piece of text (a GA or range name) implies,
    or None. Word-boundary matching over _DOMAIN_TERMS, first domain by priority;
    known location phrases are stripped first so they don't vote."""
    low = (text or "").lower()
    if not low:
        return None
    low = _LOCATION_STOP_RE.sub(" ", low)
    for dom, rx in _DOMAIN_RE.items():
        if rx.search(low):
            return dom
    return None


def _refine_category(name: str, current: str) -> str:
    """Name-domain wins over the given category, else keep it. Kept for callers
    that only have a name + a starting category (explain, tests)."""
    return _domain_from_text(name) or current


# DPTs whose category is a *soft* default because the type does not, by itself,
# pin a domain — the name / range decides. A 1-bit switch is a light as easily as
# a pump or an AC; a 5.001 scaling is a brightness OR a shutter position. For soft
# DPTs a contradicting name is NOT a conflict (it disambiguates), unlike a strong,
# domain-encoding DPT (a shutter 1.008, an HVAC-mode 20.102, a temperature 9.001).
# 1.010 start/stop is generic (vent timers too); 9.001 temperature is hvac by
# default but a weather/sensor name legitimately re-domains it without conflict.
_SOFT_DPT = {(1, 1), (1, 11), (1, 10), (5, 1), (9, 1)}
# The subset that is domain-AGNOSTIC end to end: with no name and no range signal
# these stay 'unknown' — we never infer 'lighting' from a bare 1-bit DPT. Other
# soft DPTs (5.001) keep their sensible default (brightness) when unsignalled.
_AGNOSTIC_NO_DEFAULT = {(1, 1), (1, 11)}


def _classify_category(name: str, main_name: str, middle_name: str,
                       main: Optional[int], sub: Optional[int], dpt_cat: str,
                       dpt_kind: str = "unknown") -> str:
    """Combine signals into a domain: explicit name > strong DPT > range context.

    * an explicit name domain wins — unless it *contradicts* a strong (domain-
      encoding) DPT, in which case the result is 'unknown' (a genuine conflict,
      not a silent pick — surfaced by explain_ga as 'contested');
    * a strong DPT keeps its domain;
    * for a soft DPT with no name domain, the group-range name decides;
    * with no signal at all, a bare 1-bit DPT is 'unknown' (never guessed
      'lighting'); a 5.001 falls back to its brightness default.
    """
    # Soft = the DPT does not pin the domain: the listed agnostic types, an
    # unknown category, or a category that came from a whole-main-group FALLBACK
    # (a guess by construction) rather than an exact (main, sub) table entry.
    soft = ((main, sub) in _SOFT_DPT or dpt_cat == CATEGORY_UNKNOWN_STR
            or not is_exact_dpt(main, sub))
    name_dom = _domain_from_text(name)
    if name_dom:
        if soft or name_dom == dpt_cat:
            return name_dom
        return CATEGORY_UNKNOWN_STR  # strong DPT vs explicit name -> honest unknown
    if not soft:
        return dpt_cat
    # Domain context comes from the MAIN group only — per the 3-level convention the
    # main group is the function domain, while the middle group is a sub-function
    # (Switch / Status / Parameters / "motion-detector settings") whose name carries
    # misleading domain words. Fall back to the middle name only if the main is unnamed.
    range_dom = _domain_from_text(main_name) or _domain_from_text(middle_name)
    if range_dom in _RANGE_ASSIGNABLE:
        return range_dom
    # Passive mains constrain passive GAs: a measurement sitting in a Sensors/
    # Energy/Diagnostics range is that domain (a 9.001 in "Sensors" is a sensor,
    # not a default hvac) — but a COMMAND is never retyped by a passive range.
    if dpt_kind != "command" and range_dom in ("sensor", "energy", "diagnostics"):
        return range_dom
    if (main, sub) in _AGNOSTIC_NO_DEFAULT:
        return CATEGORY_UNKNOWN_STR
    return dpt_cat


@dataclass
class GARecord:
    """Enriched group-address record used by all analysis tools."""
    address: str
    name: str
    description: str
    comment: str
    dpt_main: Optional[int]
    dpt_sub: Optional[int]
    data_secure: bool
    co_ids: list[str]
    category: str
    kind: str
    ha_platform: str
    value_type: Optional[str]
    label: str
    # Purpose of the GA: functional / reserve / logic / scratch. Non-functional
    # GAs are intentional noise (spares, internal logic, leftovers) and the
    # checks reclassify them instead of raising false errors/warnings.
    intent: str = INTENT_FUNCTIONAL
    # 3-level decomposition
    main: Optional[int] = None
    middle: Optional[int] = None
    sub: Optional[int] = None
    main_name: str = ""
    middle_name: str = ""

    @property
    def dpt(self) -> str:
        return dpt_key(self.dpt_main, self.dpt_sub)

    @property
    def middle_key(self) -> str:
        """Identity of the parent middle group (for sibling search)."""
        if self.main is not None and self.middle is not None:
            return f"{self.main}/{self.middle}"
        return ""


@dataclass
class LoadedProject:
    path: str
    info: dict[str, Any]
    gas: dict[str, GARecord]              # address -> record
    raw: KNXProject = field(repr=False)
    devices: dict[str, Any] = field(default_factory=dict, repr=False)
    functions: dict[str, Any] = field(default_factory=dict, repr=False)
    topology: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def style(self) -> str:
        return self.info.get("group_address_style", "")


def _split_three_level(address: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    parts = address.split("/")
    if len(parts) == 3:
        try:
            return int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None, None, None
    return None, None, None


def _override_kind_by_name(name: str, kind: str) -> str:
    """Refine command/status using name keywords (helps when DPT is generic)."""
    low = name.lower()
    if any(k in low for k in STATUS_KEYWORDS):
        return "status"
    if any(k in low for k in COMMAND_KEYWORDS):
        # only upgrade unknown -> command; never overwrite explicit sensor
        if kind in ("unknown", "command", "status"):
            return "command"
    return kind


def _build_range_name_map(raw: KNXProject) -> dict[str, str]:
    """Map address-prefix -> human range name from group_ranges.

    Returns keys like '1' (main) and '1/1' (middle) -> name.
    """
    out: dict[str, str] = {}

    def walk(rng: dict[str, Any], depth: int) -> None:
        start = rng.get("address_start")
        name = rng.get("name", "")
        if isinstance(start, int):
            main = (start >> 11) & 0x1F
            middle = (start >> 8) & 0x07
            # Depth decides main vs middle, NOT address arithmetic: a middle group
            # 0 starts at the same address as its main (start % 2048 == 0 too), so
            # the old modulo heuristic let "middle 0" overwrite the main's name.
            if depth == 0:
                out[str(main)] = name
            else:
                out[f"{main}/{middle}"] = name
        for child in rng.get("group_ranges", {}).values():
            walk(child, depth + 1)

    for rng in raw.get("group_ranges", {}).values():
        walk(rng, 0)
    return out


def load_project(path: str, password: Optional[str] = None,
                 language: Optional[str] = None) -> LoadedProject:
    """Parse a .knxproj file into an enriched, read-only model."""
    preflight_archive(path)  # reject zip-bomb / oversize / traversal before xknxproject reads it
    kwargs: dict[str, Any] = {"path": path}
    if password:
        kwargs["password"] = password
    if language:
        kwargs["language"] = language
    raw: KNXProject = XKNXProj(**kwargs).parse()
    return build_loaded_from_raw(raw, path)


def build_loaded_from_raw(raw: KNXProject, path: str) -> LoadedProject:
    """Build an enriched LoadedProject from an already-parsed KNXProject dict."""
    range_names = _build_range_name_map(raw)

    gas: dict[str, GARecord] = {}
    for addr, ga in raw.get("group_addresses", {}).items():
        dpt = ga.get("dpt")
        main = dpt.get("main") if dpt else None
        sub = dpt.get("sub") if dpt else None
        info = classify_dpt(main, sub)
        kind = _override_kind_by_name(ga.get("name", ""), info["kind"])
        m, mid, s = _split_three_level(ga.get("address", addr))
        main_name = range_names.get(str(m), "") if m is not None else ""
        middle_name = range_names.get(f"{m}/{mid}", "") if m is not None and mid is not None else ""
        # Domain is a COMBINATION of signals (name > strong DPT > range context),
        # not the DPT alone — a 1-bit switch is domain-agnostic, so an "AC on/off"
        # is HVAC, not lighting, and a truly context-less switch is 'unknown'.
        category = _classify_category(ga.get("name", ""), main_name, middle_name,
                                      main, sub, info["category"], info["kind"])
        ha_platform = info["ha_platform"]
        # If the name says shutter but DPT mapped it to light (5.001/1.001),
        # correct the HA platform so the generator builds a cover, not a light.
        if category == "shutter" and ha_platform in ("light", "switch"):
            ha_platform = "cover"
        # A 1-bit diagnostics GA (wind/frost/rain/smoke/leak alarm, fault) is a
        # read-only input, not a command switch -> binary_sensor.
        if category == "diagnostics" and main == 1 and ha_platform == "switch":
            ha_platform = "binary_sensor"
            kind = "sensor"
        rec = GARecord(
            address=ga.get("address", addr),
            name=ga.get("name", ""),
            description=ga.get("description", "") or "",
            comment=ga.get("comment", "") or "",
            dpt_main=main,
            dpt_sub=sub,
            data_secure=bool(ga.get("data_secure", False)),
            co_ids=list(ga.get("communication_object_ids", []) or []),
            category=category,
            kind=kind,
            ha_platform=ha_platform,
            value_type=info["value_type"],
            label=info["label"],
            intent=classify_intent(ga.get("name", "")),
            main=m, middle=mid, sub=s,
            main_name=main_name,
            middle_name=middle_name,
        )
        gas[rec.address] = rec

    return LoadedProject(
        path=path,
        info=dict(raw.get("info", {})),
        gas=gas,
        raw=raw,
        devices=dict(raw.get("devices", {})),
        functions=dict(raw.get("functions", {})),
        topology=dict(raw.get("topology", {})),
    )
