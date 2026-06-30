"""Human-readable Markdown report.

Per the safety requirement, a report like this is produced BEFORE any ETS import
or HA deployment, so a human can review what will change.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .project import LoadedProject
from .analyze import validate_naming, detect_missing_status, detect_dpt_issues
from .generate_ha import generate_ha_yaml


_SEV_ICON = {"error": "🔴", "warning": "🟡", "info": "🔵"}


def _section(title: str, findings: list[dict[str, Any]]) -> str:
    if not findings:
        return f"### {title}\n\n_No issues found._\n"
    out = [f"### {title}  ({len(findings)})\n"]
    by_sev = defaultdict(list)
    for f in findings:
        by_sev[f["severity"]].append(f)
    for sev in ("error", "warning", "info"):
        for f in by_sev.get(sev, []):
            out.append(f"- {_SEV_ICON.get(sev,'')} `{f['address']}` — {f['message']}")
    return "\n".join(out) + "\n"


def build_report(project: LoadedProject,
                 name_regex: str | None = None) -> dict[str, Any]:
    """Return {'markdown': str, 'summary': {...}}."""
    naming = validate_naming(project, name_regex=name_regex)
    status = detect_missing_status(project)
    dpts = detect_dpt_issues(project)
    ha = generate_ha_yaml(project)

    info = project.info
    gas = project.gas

    cat_counts = Counter(ga.category for ga in gas.values())
    kind_counts = Counter(ga.kind for ga in gas.values())
    intent_counts = Counter(ga.intent for ga in gas.values())
    no_dpt = sum(1 for ga in gas.values() if ga.dpt_main is None)
    secure = sum(1 for ga in gas.values() if ga.data_secure)
    non_functional = sum(v for k, v in intent_counts.items() if k != "functional")

    all_findings = naming + status + dpts
    sev_counts = Counter(f["severity"] for f in all_findings)

    md: list[str] = []
    md.append(f"# KNX Project Report — {info.get('name', '?')}\n")
    md.append(
        f"- **Source:** `{project.path}`\n"
        f"- **GA style:** {info.get('group_address_style', '?')}\n"
        f"- **ETS tool version:** {info.get('tool_version', '?')}  "
        f"(xknxproject {info.get('xknxproject_version', '?')})\n"
        f"- **Last modified:** {info.get('last_modified', '?')}\n"
    )

    md.append("\n## 1. Inventory\n")
    md.append(
        f"- Group addresses: **{len(gas)}**\n"
        f"- Devices: **{len(project.devices)}**\n"
        f"- Functions: **{len(project.functions)}**\n"
        f"- Without DPT: **{no_dpt}**\n"
        f"- KNX Data Secure GAs: **{secure}**\n"
    )
    md.append("\n**By category:** " +
              ", ".join(f"{k}={v}" for k, v in sorted(cat_counts.items())) + "\n")
    md.append("**By kind:** " +
              ", ".join(f"{k}={v}" for k, v in sorted(kind_counts.items())) + "\n")
    if non_functional:
        md.append(
            "**By purpose:** " +
            ", ".join(f"{k}={v}" for k, v in sorted(intent_counts.items())) +
            f" — {non_functional} non-functional GA(s) (reserve / logic / scratch) "
            "are excluded from error and missing-status checks to keep the report "
            "focused on real device addresses.\n"
        )

    md.append("\n## 2. Findings\n")
    md.append(
        f"Totals: 🔴 errors **{sev_counts.get('error',0)}**, "
        f"🟡 warnings **{sev_counts.get('warning',0)}**, "
        f"🔵 info **{sev_counts.get('info',0)}**\n"
    )
    md.append("\n" + _section("2.1 Naming & structure", naming))
    md.append("\n" + _section("2.2 Missing status addresses", status))
    md.append("\n" + _section("2.3 DPT consistency", dpts))

    md.append("\n## 3. Home Assistant mapping preview\n")
    c = ha["counts"]
    md.append(
        f"Entities that can be generated now: switch **{c['switch']}**, "
        f"light **{c['light']}**, cover **{c['cover']}**, "
        f"binary_sensor **{c['binary_sensor']}**, sensor **{c['sensor']}**.\n"
    )
    if ha["review"]:
        md.append(f"\n**Needs manual review ({len(ha['review'])}):**\n")
        for r in ha["review"][:50]:
            md.append(f"- `{r.get('address','-')}` {r.get('name','')} — {r['reason']}")
        if len(ha["review"]) > 50:
            md.append(f"- … and {len(ha['review']) - 50} more")
        md.append("")

    md.append("\n## 4. Next steps\n")
    md.append(
        "1. Resolve 🔴 errors (missing DPT, empty names) in ETS first.\n"
        "2. Add status/feedback GAs for every flagged command.\n"
        "3. Re-run this report until errors are clear.\n"
        "4. Generate ETS CSV/XML and HA YAML, commit to Git, then import into ETS "
        "and deploy to Home Assistant.\n"
    )

    summary = {
        "ga_count": len(gas),
        "errors": sev_counts.get("error", 0),
        "warnings": sev_counts.get("warning", 0),
        "info": sev_counts.get("info", 0),
        "missing_status": len(status),
        "intent": dict(intent_counts),
        "ha_entities": {k: v for k, v in c.items() if k != "review"},
        "ha_review": c["review"],
    }
    return {"markdown": "\n".join(md), "summary": summary}
