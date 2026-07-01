"""B3 — semantic diff between two .knxproj versions.

Turns two Git snapshots of a project into a reviewable change set: which group
addresses were added / removed, which changed DPT, name or security flag. No
mainstream tool does this (xknxproject explicitly can't); our Git-tracked, read-only
workflow is its natural home. Read-only, no bus.
"""

from __future__ import annotations

from typing import Any, Optional

from .project import load_project


def diff_projects(path_a: str, path_b: str,
                  password_a: Optional[str] = None,
                  password_b: Optional[str] = None) -> dict[str, Any]:
    """Compare two .knxproj files. `path_a` = old/base, `path_b` = new."""
    a = load_project(path_a, password=password_a)
    b = load_project(path_b, password=password_b)
    return diff_loaded(a, b)


def diff_loaded(a, b) -> dict[str, Any]:
    """Diff two already-loaded projects (testable core of diff_projects)."""
    ga_a, ga_b = a.gas, b.gas
    keys_a, keys_b = set(ga_a), set(ga_b)

    added = [{"address": k, "name": ga_b[k].name, "dpt": ga_b[k].dpt}
             for k in sorted(keys_b - keys_a)]
    removed = [{"address": k, "name": ga_a[k].name, "dpt": ga_a[k].dpt}
               for k in sorted(keys_a - keys_b)]
    dpt_changed, renamed, secure_changed = [], [], []
    for k in sorted(keys_a & keys_b):
        x, y = ga_a[k], ga_b[k]
        if (x.dpt or None) != (y.dpt or None):
            dpt_changed.append({"address": k, "name": y.name,
                                "from": x.dpt, "to": y.dpt})
        if x.name.strip() != y.name.strip():
            renamed.append({"address": k, "from": x.name, "to": y.name})
        if x.data_secure != y.data_secure:
            secure_changed.append({"address": k, "name": y.name,
                                   "from": x.data_secure, "to": y.data_secure})

    def _section(title: str, rows: list, cols) -> list[str]:
        out = [f"\n## {title} ({len(rows)})\n"]
        if not rows:
            out.append("_none_")
            return out
        out.append("| " + " | ".join(cols) + " |")
        out.append("|" + "|".join("---" for _ in cols) + "|")
        for r in rows[:500]:
            out.append("| " + " | ".join(f"`{r.get(c.lower().replace(' ','_'),'')}`"
                                          if c in ("Address",) else str(r.get(c.lower().replace(' ','_'), ''))
                                          for c in cols) + " |")
        if len(rows) > 500:
            out.append(f"| … and {len(rows)-500} more |")
        return out

    md = [f"# Project diff — {a.info.get('name','A')} → {b.info.get('name','B')}\n",
          f"- Base: **{len(ga_a)}** GA  ·  New: **{len(ga_b)}** GA  "
          f"(+{len(added)} / −{len(removed)})\n"]
    md += _section("Added", added, ["Address", "Name", "Dpt"])
    md += _section("Removed", removed, ["Address", "Name", "Dpt"])
    md += _section("DPT changed", dpt_changed, ["Address", "From", "To"])
    md += _section("Renamed", renamed, ["Address", "From", "To"])
    md += _section("Security flag changed", secure_changed, ["Address", "From", "To"])

    return {
        "base_ga": len(ga_a), "new_ga": len(ga_b),
        "added": len(added), "removed": len(removed),
        "dpt_changed": len(dpt_changed), "renamed": len(renamed),
        "secure_changed": len(secure_changed),
        "markdown": "\n".join(md),
        "detail": {"added": added, "removed": removed, "dpt_changed": dpt_changed,
                   "renamed": renamed, "secure_changed": secure_changed},
    }
