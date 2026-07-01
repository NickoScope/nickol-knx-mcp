"""Repair-suggestion engine (B1) — propose fixes, don't just flag problems.

Every converter refuses on an imperfect `.knxproj`. This module does the opposite:
for each finding it proposes a concrete, reviewable fix — infer a DPT from the name,
synthesise a status group address in a free slot, add an absolute-brightness GA — so
an imperfect project can be *repaired* toward import-ready. Suggestions only: a human
reviews them, and accepted new GAs feed ``generate_ets_group_addresses``. The server
never writes to a bus or to ETS.
"""

from __future__ import annotations

from typing import Any, Optional

from .project import LoadedProject
from .analyze import detect_missing_status, detect_dpt_issues, _expected_subdpt
from .intent import INTENT_FUNCTIONAL


# command DPT main -> the status/feedback DPT to synthesise for it
_STATUS_DPT = {1: "1.011", 3: "5.001", 5: "5.001", 9: "9.001",
               13: "13.013", 14: "14.056", 20: "20.102"}


def _infer_dpt(ga: Any) -> str:
    """Best-effort DPT for a GA that has none, from its name/category/kind."""
    exp = _expected_subdpt(ga.name)
    if exp:
        return f"{exp[0]}.{exp[1]:03d}"
    low = (ga.name or "").lower()
    if ga.kind == "status" or any(k in low for k in ("статус", "status", "rück", "rueck")):
        return "1.011"
    if any(k in low for k in ("вверх/вниз", "up/down", "auf/ab", "up-down")):
        return "1.008"
    if "стоп" in low or "stop" in low:
        return "1.010"
    if "позиц" in low or "position" in low or "stellung" in low:
        return "5.001"
    if any(k in low for k in ("диммир", "dimming", "яркост", "brightness")):
        return "5.001"
    if "сцен" in low or "scene" in low or "szene" in low:
        return "18.001"
    if ga.category == "shutter":
        return "1.008"
    # switch-like boolean is the safest default
    return "1.001"


def _next_free(used: set[str], main: int, prefer_middle: Optional[int] = None) -> Optional[str]:
    """Suggest a free 3-level address in ``main`` (prefer a given middle first)."""
    order = ([prefer_middle] if prefer_middle is not None else []) + list(range(8))
    seen = set()
    for mid in order:
        if mid in seen:
            continue
        seen.add(mid)
        for sub in range(1, 256):
            a = f"{main}/{mid}/{sub}"
            if a not in used:
                used.add(a)
                return a
    return None


def suggest_repairs(project: LoadedProject) -> dict[str, Any]:
    """Propose concrete fixes for the project's findings. Suggestions only."""
    used = set(project.gas.keys())
    proposals: list[dict[str, Any]] = []

    for f in detect_dpt_issues(project):
        code = f["code"]
        addr = f["address"]
        if code == "missing_dpt" and addr in project.gas:
            ga = project.gas[addr]
            proposals.append({
                "code": code, "action": "set_dpt", "address": addr, "name": ga.name,
                "dpt": _infer_dpt(ga),
                "rationale": "inferred from the name/category so HA can decode it",
            })
        elif code == "subdpt_suspect":
            proposals.append({
                "code": code, "action": "change_dpt", "address": addr,
                "name": f.get("name"), "dpt": f.get("expected"),
                "rationale": "expected sub-type for this named function",
            })
        elif code == "relative_only_dimming" and addr in project.gas:
            ga = project.gas[addr]
            new = _next_free(used, ga.main if ga.main is not None else 1)
            proposals.append({
                "code": code, "action": "add_ga", "address": new, "for": addr,
                "name": f"{ga.name} - Значение яркости", "dpt": "5.001",
                "rationale": "absolute-brightness GA so Home Assistant can set a level",
            })

    for f in detect_missing_status(project):
        if f["code"] != "missing_status_address":
            continue
        addr = f["address"]
        ga = project.gas.get(addr)
        if ga is None:
            continue
        sdpt = _STATUS_DPT.get(ga.dpt_main, "1.011")
        new = _next_free(used, ga.main if ga.main is not None else 1, prefer_middle=4)
        proposals.append({
            "code": "missing_status", "action": "add_ga", "address": new, "for": addr,
            "name": f"{ga.name} (статус)", "dpt": sdpt,
            "rationale": "status/feedback GA so Home Assistant reads real state",
        })

    by_action: dict[str, int] = {}
    for p in proposals:
        by_action[p["action"]] = by_action.get(p["action"], 0) + 1

    return {
        "count": len(proposals),
        "by_action": by_action,
        "proposals": proposals,
        "note": "Suggestions only — review before applying. `set_dpt`/`change_dpt` edit an "
                "existing GA in ETS; `add_ga` addresses are suggested FREE slots (adjust to "
                "your convention), then feed the accepted new GAs to "
                "`generate_ets_group_addresses`. This server never writes to ETS or the bus.",
    }
