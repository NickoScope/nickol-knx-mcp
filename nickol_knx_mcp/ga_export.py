"""Read an ETS group-address export (ga-export/01 XML) as a project without devices.

A full ``.knxproj`` is not always what people have. ETS can export just the group
addresses, and planning tools (TapPlan and others) produce the same format for
import into ETS. That file carries names, addresses, DPTs, descriptions, the
security flag and the range tree, which is everything the GA-level checks and the
Home Assistant / ETS generators work on.

The export is turned into the same raw shape xknxproject produces for the group
address part, then goes through the normal ``build_loaded_from_raw``. Devices,
communication objects, ETS Functions and topology are simply empty, so the
device-level tools have nothing to report rather than guessing.

The file is untrusted input: size-capped and parsed through ``safe_fromstring``
(no DTD, no entities, no external fetches).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional, cast

from .project import LoadedProject, build_loaded_from_raw
from .safexml import SafeXmlError, safe_fromstring

MAX_EXPORT_BYTES = 50 * 1024 * 1024   # a 15 000-GA export is a few MB; this only bounds abuse
MAX_RANGE_DEPTH = 8                   # ETS nests main/middle (2); planning tools rarely go deeper

_DPT_RE = re.compile(r"^DPS?T-(\d+)(?:-(\d+))?$", re.IGNORECASE)


class GaExportError(ValueError):
    """The file is not a readable ETS group-address export."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_dpt(value: Optional[str]) -> Optional[dict[str, Optional[int]]]:
    """'DPST-1-1' -> {main 1, sub 1}; 'DPT-9' -> {main 9, sub None}; several -> the first."""
    if not value:
        return None
    first = re.split(r"[\s,;]+", value.strip())[0]
    m = _DPT_RE.match(first)
    if not m:
        return None
    return {"main": int(m.group(1)), "sub": int(m.group(2)) if m.group(2) else None}


def _raw_address(address: str) -> Optional[int]:
    try:
        parts = [int(x) for x in address.split("/")]
    except ValueError:
        return None
    if len(parts) == 3 and parts[0] <= 31 and parts[1] <= 7 and parts[2] <= 255:
        return (parts[0] << 11) | (parts[1] << 8) | parts[2]
    if len(parts) == 2 and parts[0] <= 31 and parts[1] <= 2047:
        return (parts[0] << 11) | parts[1]
    if len(parts) == 1 and 0 <= parts[0] <= 65535:
        return parts[0]
    return None


def _style(addresses: list[str]) -> str:
    depths = {a.count("/") for a in addresses}
    if depths == {2}:
        return "ThreeLevel"
    if depths == {1}:
        return "TwoLevel"
    if depths == {0}:
        return "Free"
    return "Mixed" if depths else ""


def read_ga_export_bytes(data: bytes, name: str = "ga-export") -> dict[str, Any]:
    """Parse export bytes into the raw project dict (no devices). Raises GaExportError."""
    try:
        root = safe_fromstring(data)
    except SafeXmlError as e:
        raise GaExportError(str(e)) from e
    if _local(root.tag) != "GroupAddress-Export":
        raise GaExportError(f"not an ETS group-address export (root element is <{_local(root.tag)}>)")

    gas: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    def walk_range(el, depth: int = 1) -> dict[str, Any]:
        if depth > MAX_RANGE_DEPTH:
            raise GaExportError(f"group ranges nested deeper than {MAX_RANGE_DEPTH} levels — refused")
        start = el.get("RangeStart")
        end = el.get("RangeEnd")
        rng: dict[str, Any] = {
            "name": el.get("Name", ""),
            "address_start": int(start) if start and start.isdigit() else None,
            "address_end": int(end) if end and end.isdigit() else None,
            "comment": el.get("Description", ""),
            "group_addresses": [],
            "group_ranges": {},
        }
        for child in el:
            tag = _local(child.tag)
            if tag == "GroupRange":
                sub = walk_range(child, depth + 1)
                rng["group_ranges"][f"{sub['name']}@{sub['address_start']}"] = sub
            elif tag == "GroupAddress":
                addr = add_ga(child)
                if addr:
                    rng["group_addresses"].append(addr)
        return rng

    def add_ga(el) -> Optional[str]:
        address = (el.get("Address") or "").strip()
        raw = _raw_address(address)
        if raw is None:
            warnings.append(f"skipped group address with invalid Address {address!r}")
            return None
        if address in gas:
            warnings.append(f"duplicate address {address} — kept the first entry")
            return None
        dpts = el.get("DPTs")
        dpt = parse_dpt(dpts)
        if dpts and dpt is None:
            warnings.append(f"{address}: DPT {dpts!r} not understood, left unset")
        gas[address] = {
            "name": el.get("Name", ""),
            "identifier": f"GA-{raw}",
            "raw_address": raw,
            "address": address,
            "project_uid": None,
            "dpt": dpt,
            "data_secure": (el.get("Security") or "").strip().lower() == "on",
            "communication_object_ids": [],
            "description": el.get("Description", "") or "",
            "comment": "",
        }
        return address

    ranges: dict[str, Any] = {}
    for child in root:
        tag = _local(child.tag)
        if tag == "GroupRange":
            rng = walk_range(child)
            ranges[f"{rng['name']}@{rng['address_start']}"] = rng
        elif tag == "GroupAddress":
            add_ga(child)

    info = {
        "name": name,
        "source": "ga-export",
        "group_address_style": _style(list(gas)),
        "tool_version": None,
        "import_warnings": warnings,
    }
    return {"info": info, "group_addresses": gas, "group_ranges": ranges, "devices": {},
            "communication_objects": {}, "functions": {}, "locations": {}, "topology": {}}


def load_ga_export(path: str) -> LoadedProject:
    """Load an ETS ga-export/01 XML file as a read-only project without devices."""
    if not os.path.isfile(path):
        raise GaExportError(f"file not found: {path}")
    size = os.path.getsize(path)
    if size > MAX_EXPORT_BYTES:
        raise GaExportError(f"file is {size} bytes, over the {MAX_EXPORT_BYTES}-byte limit")
    with open(path, "rb") as fh:
        data = fh.read(MAX_EXPORT_BYTES + 1)
    raw = read_ga_export_bytes(data, name=Path(path).stem)
    return build_loaded_from_raw(cast(Any, raw), path)
