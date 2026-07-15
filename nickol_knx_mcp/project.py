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

from .dpt_map import classify_dpt, dpt_key
from .intent import classify_intent, INTENT_FUNCTIONAL
from .safexml import preflight_archive


# Multilingual keyword sets (EN / DE / RU) used by the heuristic fallbacks.
STATUS_KEYWORDS = [
    "status", "state", "stat", "fb", "feedback", "rueck", "rück", "rm ",
    "rm_", "статус", "состоян", "обратн", "сост.",
]
COMMAND_KEYWORDS = [
    "switch", "schalt", "dimm", "control", "steuer", "befehl", "set",
    "soll", "вкл", "выкл", "упр", "команд", "задан",
]

# Category disambiguation by name (used for DPTs ambiguous between domains,
# e.g. 5.001 = brightness OR shutter position; 1.001 = light OR generic).
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "shutter": ["blind", "shutter", "jalousie", "roll", "rollo", "marqui",
                "awning", "curtain", "position", "behang", "lamelle",
                "raffstore", "markise", "auf/ab", "ab/auf", "штор", "жалюзи",
                "рольставн", "ролет", "ролл", "позиц", "вверх/вниз", "ламел"],
    "lighting": ["light", "lamp", "dimm", "led", "spot", "свет", "лампа",
                 "подсветк", "освещ", "люстра", "диммер"],
    "hvac": ["heat", "cool", "climate", "thermostat", "hvac", "valve", "fan",
             "отопл", "климат", "тепл", "конвектор", "вентил", "клапан",
             "кондиц", "тёпл"],
    "energy": ["energy", "power", "consum", "meter", "kwh", "watt", "энерг",
               "мощност", "потребл", "счётчик", "счетчик"],
    "scene": ["scene", "scene", "сцен", "preset", "пресет"],
    "diagnostics": ["alarm", "fault", "error", "diag", "leak", "smoke",
                    "тревог", "ошибк", "диагност", "утечк", "дым"],
}


def _refine_category(name: str, current: str) -> str:
    low = name.lower()
    for cat, words in _CATEGORY_KEYWORDS.items():
        if any(w in low for w in words):
            return cat
    return current


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

    def walk(rng: dict[str, Any]) -> None:
        start = rng.get("address_start")
        name = rng.get("name", "")
        if isinstance(start, int):
            # main range: start aligned to 0x0800 boundaries; derive main number
            main = (start >> 11) & 0x1F
            middle = (start >> 8) & 0x07
            # heuristic: if start is multiple of 2048 -> a main range, else middle
            if start % 2048 == 0:
                out[str(main)] = name
            else:
                out[f"{main}/{middle}"] = name
        for child in rng.get("group_ranges", {}).values():
            walk(child)

    for rng in raw.get("group_ranges", {}).values():
        walk(rng)
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
        category = _refine_category(ga.get("name", ""), info["category"])
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
        m, mid, s = _split_three_level(ga.get("address", addr))
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
            main_name=range_names.get(str(m), "") if m is not None else "",
            middle_name=range_names.get(f"{m}/{mid}", "") if m is not None and mid is not None else "",
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
