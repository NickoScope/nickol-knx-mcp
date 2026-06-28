"""Generate ETS-importable Group Address exports (CSV + XML).

XML uses the official ETS GA-export schema (http://knx.org/xml/ga-export/01),
which is the most reliable import path. CSV uses the native ETS group-address
layout (group name + X/Y/Z address with -/- range placeholders).

Neither export touches a live bus. The intended flow is: generate -> review the
human-readable report -> import into ETS via 'Import Group Addresses'.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Optional
from xml.sax.saxutils import escape

from .project import LoadedProject
from .dpt_map import dpt_ets_token


def _hierarchy(project: LoadedProject) -> dict[int, dict[str, Any]]:
    """Build {main: {name, middles: {middle: {name, gas: [rec]}}}}.

    Range names come from raw group_ranges when available, otherwise synthesized.
    """
    # raw range names indexed by (main) and (main, middle)
    main_names: dict[int, str] = {}
    mid_names: dict[tuple[int, int], str] = {}

    def walk(rng: dict[str, Any]) -> None:
        start = rng.get("address_start")
        name = rng.get("name", "")
        if isinstance(start, int):
            main = (start >> 11) & 0x1F
            middle = (start >> 8) & 0x07
            if start % 2048 == 0 and not rng.get("group_addresses"):
                main_names.setdefault(main, name)
            else:
                mid_names.setdefault((main, middle), name)
        for child in rng.get("group_ranges", {}).values():
            walk(child)

    for rng in project.raw.get("group_ranges", {}).values():
        walk(rng)

    tree: dict[int, dict[str, Any]] = {}
    for ga in project.gas.values():
        if ga.main is None or ga.middle is None:
            continue
        m = tree.setdefault(ga.main, {
            "name": main_names.get(ga.main) or ga.main_name or f"Main group {ga.main}",
            "middles": {},
        })
        mid = m["middles"].setdefault(ga.middle, {
            "name": mid_names.get((ga.main, ga.middle)) or ga.middle_name
            or f"Middle group {ga.main}/{ga.middle}",
            "gas": [],
        })
        mid["gas"].append(ga)
    return tree


def _security(ga) -> str:
    return "On" if ga.data_secure else "Auto"


def generate_ets_csv(project: LoadedProject) -> str:
    """Native ETS GA CSV (semicolon-separated, with range placeholder rows)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["Group name", "Address", "Central", "Unfiltered",
                "Description", "DatapointType", "Security"])
    tree = _hierarchy(project)
    for main in sorted(tree):
        m = tree[main]
        w.writerow([m["name"], f"{main}/-/-", "", "", "", "", ""])
        for middle in sorted(m["middles"]):
            mid = m["middles"][middle]
            w.writerow([mid["name"], f"{main}/{middle}/-", "", "", "", "", ""])
            for ga in sorted(mid["gas"], key=lambda g: g.sub or 0):
                w.writerow([
                    ga.name, ga.address, "", "",
                    ga.description or ga.comment or "",
                    dpt_ets_token(ga.dpt_main, ga.dpt_sub),
                    _security(ga),
                ])
    return buf.getvalue()


def generate_ets_xml(project: LoadedProject) -> str:
    """ETS GA-export/01 XML."""
    tree = _hierarchy(project)
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<GroupAddress-Export xmlns="http://knx.org/xml/ga-export/01">',
    ]
    for main in sorted(tree):
        m = tree[main]
        m_start = main << 11
        m_end = m_start | 0x7FF
        lines.append(
            f'  <GroupRange Name="{escape(m["name"], {chr(34): "&quot;"})}" '
            f'RangeStart="{m_start}" RangeEnd="{m_end}">'
        )
        for middle in sorted(m["middles"]):
            mid = m["middles"][middle]
            mid_start = (main << 11) | (middle << 8)
            mid_end = mid_start | 0xFF
            lines.append(
                f'    <GroupRange Name="{escape(mid["name"], {chr(34): "&quot;"})}" '
                f'RangeStart="{mid_start}" RangeEnd="{mid_end}">'
            )
            for ga in sorted(mid["gas"], key=lambda g: g.sub or 0):
                dpts = dpt_ets_token(ga.dpt_main, ga.dpt_sub)
                dpt_attr = f' DPTs="{dpts}"' if dpts else ""
                desc = ga.description or ga.comment or ""
                desc_attr = f' Description="{escape(desc, {chr(34): "&quot;"})}"' if desc else ""
                sec_attr = ' Security="On"' if ga.data_secure else ""
                lines.append(
                    f'      <GroupAddress Name="{escape(ga.name, {chr(34): "&quot;"})}" '
                    f'Address="{ga.address}"{dpt_attr}{desc_attr}{sec_attr} />'
                )
            lines.append('    </GroupRange>')
        lines.append('  </GroupRange>')
    lines.append('</GroupAddress-Export>')
    return "\n".join(lines) + "\n"
