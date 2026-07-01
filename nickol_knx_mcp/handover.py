"""Project handover pack — the deliverable an integrator hands over at commissioning.

From a read-only ``.knxproj`` this assembles the "as-built" picture the next
engineer (or the client) needs: an **equipment inventory** by manufacturer, the
**group-address map by domain**, **command/status feedback coverage**, the
**KNX Secure scope**, and the current **QA state** — plus a standalone **SVG
topology diagram**. It reuses the existing analysis passes so the numbers match
``project_report``; it adds the packaging, structure and diagram that turn a bag
of findings into a handover document.

No bus access, no writes outside the caller-provided path. Pure text + SVG.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from html import escape
from typing import Any

from .project import LoadedProject
from .analyze import validate_naming, detect_missing_status, detect_dpt_issues
from .intent import INTENT_FUNCTIONAL


# --------------------------------------------------------------------------- #
# Structure helpers
# --------------------------------------------------------------------------- #
def _range_names(project: LoadedProject) -> tuple[dict[int, str], dict[tuple[int, int], str]]:
    """Authoritative main/middle names from the project's GroupRanges.

    ``GARecord.main_name`` from the parser can mislabel (it may carry a middle
    range's name), so the domain map reads names straight from ``group_ranges``.
    """
    main_names: dict[int, str] = {}
    mid_names: dict[tuple[int, int], str] = {}
    for mkey, mrange in (project.raw.get("group_ranges") or {}).items():
        head = str(mkey).split("/")[0]
        if not head.isdigit():
            continue
        mi = int(head)
        main_names[mi] = mrange.get("name") or ""
        for skey, srange in (mrange.get("group_ranges") or {}).items():
            parts = str(skey).split("/")
            if len(parts) >= 2 and parts[1].isdigit():
                mid_names[(mi, int(parts[1]))] = srange.get("name") or ""
    return main_names, mid_names


def _domain_map(project: LoadedProject) -> dict[int, dict[str, Any]]:
    """main -> {name, count, middles: {middle -> {name, count}}}, sorted-ready."""
    main_names, mid_names = _range_names(project)
    mains: dict[int, dict[str, Any]] = {}
    for ga in project.gas.values():
        if ga.main is None:
            continue
        m = mains.setdefault(
            ga.main, {"name": main_names.get(ga.main, ""), "count": 0, "middles": {}})
        m["count"] += 1
        midkey = ga.middle if ga.middle is not None else -1
        mid = m["middles"].setdefault(
            midkey, {"name": mid_names.get((ga.main, midkey), ""), "count": 0})
        mid["count"] += 1
    return mains


def _device_inventory(project: LoadedProject) -> dict[str, list[dict[str, Any]]]:
    """manufacturer -> [ {ia, name, order, cos} ], each list sorted by IA."""
    by_mfr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in project.devices.values():
        by_mfr[d.get("manufacturer_name") or "?"].append({
            "ia": d.get("individual_address") or "?",
            "name": d.get("name") or "?",
            "order": d.get("order_number") or "?",
            "cos": len(d.get("communication_object_ids", []) or []),
        })
    for lst in by_mfr.values():
        lst.sort(key=lambda x: x["ia"])
    return by_mfr


def _feedback_coverage(project: LoadedProject,
                       missing: list[dict[str, Any]]) -> dict[str, int]:
    """How many functional command GAs have a status vs are missing one."""
    commands = [ga for ga in project.gas.values()
                if ga.intent == INTENT_FUNCTIONAL and ga.kind == "command"
                and ga.dpt_main is not None]
    gaps = sum(1 for f in missing if f["code"] == "missing_status_address")
    total = len(commands)
    return {"commands": total, "with_status": max(total - gaps, 0), "missing": gaps}


# --------------------------------------------------------------------------- #
# SVG topology diagram (standalone, no external CSS)
# --------------------------------------------------------------------------- #
def build_topology_svg(project: LoadedProject) -> str:
    """A simple, valid, standalone SVG of areas -> lines -> device counts."""
    areas = project.topology or {}
    W = 820
    pad, row_h, gap = 20, 34, 10
    rows: list[tuple[str, str, str, int]] = []  # (kind, id, label, devices)
    for aid, area in areas.items():
        lines = area.get("lines", {}) or {}
        adev = sum(len(l.get("devices", []) or []) for l in lines.values())
        rows.append(("area", str(aid), area.get("name") or f"Area {aid}", adev))
        for lid, line in lines.items():
            n = len(line.get("devices", []) or [])
            label = f"{lid}  {line.get('name') or ''}".strip()
            rows.append(("line", str(lid), label, n))
    if not rows:
        rows = [("area", "-", "No topology in project", 0)]

    max_dev = max((n for _, _, _, n in rows if n), default=1) or 1
    H = pad * 2 + len(rows) * (row_h + gap) + 40
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="Segoe UI, Arial, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="{pad}" y="{pad+8}" font-size="15" font-weight="700" '
        f'fill="#1f2937">KNX topology — {escape(project.info.get("name","?"))}</text>',
    ]
    y = pad + 28
    for kind, rid, label, n in rows:
        if kind == "area":
            out.append(
                f'<rect x="{pad}" y="{y}" width="{W-2*pad}" height="{row_h}" rx="6" '
                f'fill="#1f2937"/>'
                f'<text x="{pad+12}" y="{y+22}" font-size="13" font-weight="700" '
                f'fill="#ffffff">▣ {escape(label)}  ·  {n} devices</text>'
            )
        else:
            bar = int((W - 2 * pad - 340) * (n / max_dev)) if n else 0
            out.append(
                f'<rect x="{pad+24}" y="{y}" width="{W-2*pad-24}" height="{row_h}" rx="6" '
                f'fill="#eef2ff" stroke="#c7d2fe"/>'
                f'<text x="{pad+36}" y="{y+22}" font-size="12" fill="#3730a3">'
                f'{escape(label)}</text>'
                f'<rect x="{W-pad-300}" y="{y+9}" width="{bar}" height="{row_h-18}" rx="3" '
                f'fill="#6366f1"/>'
                f'<text x="{W-pad-12}" y="{y+22}" font-size="12" text-anchor="end" '
                f'fill="#4338ca" font-weight="600">{n} dev</text>'
            )
        y += row_h + gap
    out.append('</svg>')
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Handover document (Markdown)
# --------------------------------------------------------------------------- #
def build_handover(project: LoadedProject,
                   name_regex: str | None = None) -> dict[str, Any]:
    """Return {'markdown': str, 'svg': str, 'summary': {...}}."""
    naming = validate_naming(project, name_regex=name_regex)
    missing = detect_missing_status(project)
    dpts = detect_dpt_issues(project)
    all_f = naming + missing + dpts
    sev = Counter(f["severity"] for f in all_f)

    gas = project.gas
    info = project.info
    inv = _device_inventory(project)
    dmap = _domain_map(project)
    cover = _feedback_coverage(project, missing)
    secure = [ga for ga in gas.values() if ga.data_secure]
    intent_counts = Counter(ga.intent for ga in gas.values())

    md: list[str] = []
    md.append(f"# KNX Handover Pack — {info.get('name','?')}\n")
    md.append(
        "_As-built handover document generated read-only from the ETS project. "
        "Review before commissioning sign-off; this server never touches the bus._\n"
    )
    md.append(
        f"- **Source project:** `{info.get('name','?')}`\n"
        f"- **GA style:** {info.get('group_address_style','?')}  ·  "
        f"**ETS tool:** {info.get('tool_version','?')}\n"
        f"- **Last modified:** {info.get('last_modified','?')}\n"
        f"- **Group addresses:** {len(gas)}  ·  **Devices:** {len(project.devices)}  ·  "
        f"**Lines:** {sum(len(a.get('lines',{})) for a in project.topology.values())}\n"
    )

    # 1. Topology
    md.append("\n## 1. Topology\n")
    md.append("See `topology.svg` for the diagram. Lines and device counts:\n")
    md.append("| Line | Name | Medium | Devices |")
    md.append("|---|---|---|---|")
    for aid, area in project.topology.items():
        for lid, line in area.get("lines", {}).items():
            md.append(f"| `{lid}` | {line.get('name','')} | {line.get('medium_type','')} "
                      f"| {len(line.get('devices',[]) or [])} |")

    # 2. Equipment inventory (Спецификация оборудования)
    md.append("\n## 2. Equipment inventory\n")
    for mfr in sorted(inv):
        devs = inv[mfr]
        md.append(f"\n**{mfr}** — {len(devs)} device(s)\n")
        md.append("| IA | Device | Order № | Comm-objects |")
        md.append("|---|---|---|---|")
        for d in devs:
            md.append(f"| `{d['ia']}` | {d['name']} | `{d['order']}` | {d['cos']} |")

    # 3. Group-address map by domain
    md.append("\n## 3. Group-address map by domain\n")
    for main in sorted(dmap):
        m = dmap[main]
        md.append(f"\n**[{main}] {m['name'] or '(unnamed)'}** — {m['count']} GA\n")
        for mid in sorted(m["middles"]):
            sub = m["middles"][mid]
            label = f".{mid}" if mid >= 0 else ".-"
            md.append(f"- `{label}` {sub['name'] or '(unnamed)'} — {sub['count']} GA")

    # 4. Feedback coverage
    md.append("\n## 4. Command / status coverage\n")
    pct = (100 * cover["with_status"] // cover["commands"]) if cover["commands"] else 0
    md.append(
        f"- Functional command GAs: **{cover['commands']}**\n"
        f"- With a status/feedback GA: **{cover['with_status']}** ({pct}%)\n"
        f"- Missing status: **{cover['missing']}** — Home Assistant cannot read real "
        "state for these until a feedback GA is added.\n"
    )

    # 5. KNX Secure
    md.append("\n## 5. KNX Secure scope\n")
    if secure:
        md.append(
            f"**{len(secure)}** group address(es) carry the KNX Data Secure flag. "
            "The next engineer needs the **ETS Keyring export (`.knxkeys`)** to "
            "commission or read these — it is handled in ETS/HA, never by this tool.\n"
        )
        md.append("\n<details><summary>Secured group addresses</summary>\n")
        for ga in secure[:200]:
            md.append(f"- `{ga.address}` {ga.name}")
        if len(secure) > 200:
            md.append(f"- … and {len(secure)-200} more")
        md.append("</details>\n")
    else:
        md.append("No KNX Data Secure group addresses in this project.\n")

    # 6. QA state at handover — itemised findings
    md.append("\n## 6. QA state at handover\n")
    md.append(
        f"Totals: 🔴 errors **{sev.get('error',0)}**, "
        f"🟡 warnings **{sev.get('warning',0)}**, 🔵 info **{sev.get('info',0)}**.\n"
    )
    _SEV = {"error": "🔴", "warning": "🟡", "info": "🔵"}
    _ORD = {"error": 0, "warning": 1, "info": 2}
    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in all_f:
        by_code[f["code"]].append(f)
    # Itemise errors + warnings (info = intentional reserves/logic/macros, not defects)
    for code in sorted(by_code, key=lambda c: (_ORD.get(by_code[c][0]["severity"], 3), -len(by_code[c]))):
        items = by_code[code]
        sv = items[0]["severity"]
        if sv == "info":
            continue
        md.append(f"\n**{_SEV.get(sv,'')} `{code}` — {len(items)}**\n")
        for f in items[:20]:
            nm = f.get("name", "")
            md.append(f"- `{f['address']}`{(' — ' + nm) if nm else ''}")
        if len(items) > 20:
            md.append(f"- … and {len(items)-20} more")
    nonfunc = ", ".join(f"{k}={v}" for k, v in sorted(intent_counts.items()) if k != INTENT_FUNCTIONAL)
    if nonfunc:
        md.append(f"\nNon-functional GAs excluded from error checks (intentional): {nonfunc}.\n")
    md.append("\nResolve 🔴 errors in ETS before sign-off.\n")

    # 7. Pack contents
    md.append("\n## 7. Pack contents\n")
    md.append(
        "- `handover.md` — this document.\n"
        "- `topology.svg` — area/line/device diagram.\n"
        "- `group-addresses.csv` — full GA list (ETS-native export).\n"
        "- `ha-package.yaml` — Home Assistant KNX package (optional deploy).\n"
    )

    summary = {
        "ga_count": len(gas),
        "devices": len(project.devices),
        "manufacturers": len(inv),
        "lines": sum(len(a.get("lines", {})) for a in project.topology.values()),
        "domains": len(dmap),
        "feedback_coverage_pct": pct,
        "secure_gas": len(secure),
        "errors": sev.get("error", 0),
        "warnings": sev.get("warning", 0),
    }
    return {"markdown": "\n".join(md), "svg": build_topology_svg(project),
            "summary": summary}
