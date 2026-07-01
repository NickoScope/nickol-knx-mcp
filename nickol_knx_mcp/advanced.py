"""Advanced analysis + generators (roadmap tier B/C).

All read-only, design-time. Each function takes a LoadedProject and returns plain
data / Markdown for review — nothing here touches ETS or a bus.

  B4 test_protocol       - per-function acceptance checklist (command -> expected status)
  B5 matter_readiness    - which functions map cleanly to a Matter cluster, what's missing
  B6 energy_scaffold     - metering/energy domain check + a suggested structure
  C2 suggest_naming      - propose zone+function names / normalise status tokens
  C3 completeness_grade  - grade a project: bare skeleton vs as-built
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .project import LoadedProject
from .pairing import find_status, base_tokens
from .intent import INTENT_FUNCTIONAL


def _functional_commands(project: LoadedProject) -> list:
    return [g for g in project.gas.values()
            if g.intent == INTENT_FUNCTIONAL and g.kind == "command"
            and g.dpt_main is not None]


def _status_gas(project: LoadedProject) -> list:
    from .analyze import _is_status_ga
    return [g for g in project.gas.values() if _is_status_ga(g)]


# --------------------------------------------------------------------------- #
# B5 — Matter readiness
# --------------------------------------------------------------------------- #
_MATTER = {
    "lighting": ("OnOff / LevelControl", ("on/off", "brightness+status")),
    "shutter": ("WindowCovering", ("up/down", "position+status")),
    "hvac": ("Thermostat", ("setpoint", "mode", "status")),
    "climate": ("Thermostat", ("setpoint", "mode", "status")),
    "sensor": ("sensor cluster", ("value",)),
    "energy": ("ElectricalMeasurement", ("value",)),
}


def matter_readiness(project: LoadedProject) -> dict[str, Any]:
    """Which controllable functions round-trip to a Matter cluster, and what's missing."""
    stats = _status_gas(project)
    ready, not_ready = [], []
    for ga in _functional_commands(project):
        cluster = _MATTER.get(ga.category)
        if cluster is None:
            continue
        has_status = find_status(ga, [s for s in stats if s.main == ga.main]) is not None \
            or find_status(ga, stats) is not None
        row = {"address": ga.address, "name": ga.name, "category": ga.category,
               "matter": cluster[0], "has_status": has_status}
        (ready if has_status else not_ready).append(row)
    total = len(ready) + len(not_ready)
    return {
        "controllable_functions": total,
        "matter_ready": len(ready),
        "ready_pct": (100 * len(ready) // total) if total else 0,
        "not_ready": not_ready[:200],
        "note": "Ready = has a status GA + decodable DPT, so the Matter cluster can report "
                "state. A Matter bridge (e.g. HA Matter server) exposes these; functions "
                "without a status GA won't round-trip. Static readiness only — no bridging here.",
    }


# --------------------------------------------------------------------------- #
# C3 — as-built completeness grader
# --------------------------------------------------------------------------- #
_PATTERNS = {
    "central macros": ("общее", "все ", "всё", "central", "all "),
    "motion tuning": ("порог освещ", "блокировк", "время, сек", "тест-режим", "чувствит"),
    "astro / meteo": ("солнц", "азимут", "восход", "закат", "метео", "sun ", "meteo"),
    "monitoring": ("мониторинг", "статус работы", "неисправ", "monitoring", "fault"),
    "deep metering": ("счётчик", "потреблен", "тариф", "meter", "consumption"),
    "scenes": ("сцена", "сценар", "scene", "szene"),
    "reserves": ("резерв", "reserve", "spare"),
    "debug main": ("отладк", "временно", "debug", "logic for"),
}


def completeness_grade(project: LoadedProject) -> dict[str, Any]:
    """Grade a project: bare functional skeleton vs as-built grade (§ alex-skill patterns)."""
    names = " \n ".join(g.name.lower() for g in project.gas.values())
    present, missing = {}, []
    for label, toks in _PATTERNS.items():
        n = sum(names.count(t) for t in toks)
        present[label] = n
        if n == 0:
            missing.append(label)
    hit = sum(1 for v in present.values() if v)
    score = round(100 * hit / len(_PATTERNS))
    grade = ("as-built grade" if score >= 75 else
             "near-complete" if score >= 55 else
             "functional skeleton" if score >= 30 else "bare skeleton")
    return {
        "grade": grade, "score": score,
        "patterns_present": {k: v for k, v in present.items() if v},
        "patterns_missing": missing,
        "note": "Completeness = presence of the as-built patterns a professional adds beyond "
                "the bare functional set (central macros, device tuning, astro/meteo, "
                "monitoring, deep metering, scenes, reserves, a debug main). Not a "
                "correctness score — a project can be correct yet a bare skeleton.",
    }


# --------------------------------------------------------------------------- #
# B6 — energy-domain check + scaffold
# --------------------------------------------------------------------------- #
_ENERGY_DPT = {13: "13.013 (energy Wh/kWh)", 14: "14.056 (power W)"}


def energy_scaffold(project: LoadedProject) -> dict[str, Any]:
    """Check the metering/energy domain and suggest a structure."""
    meters = [g for g in project.gas.values()
              if any(t in g.name.lower() for t in
                     ("счётчик", "потреблен", "энерг", "мощност", "power", "energy", "meter", "квтч", "kwh"))]
    bad = [{"address": g.address, "name": g.name, "dpt": g.dpt}
           for g in meters if g.dpt_main not in (13, 14) and g.dpt_main is not None]
    scaffold = [
        {"function": "Per-circuit consumption", "dpt": "13.013", "role": "status"},
        {"function": "Per-circuit power", "dpt": "14.056", "role": "status"},
        {"function": "PV production", "dpt": "13.013", "role": "status"},
        {"function": "Battery state of charge", "dpt": "5.001", "role": "status"},
        {"function": "EVSE charging power", "dpt": "14.056", "role": "status"},
        {"function": "Grid import/export", "dpt": "13.013", "role": "status"},
    ]
    return {
        "metering_gas": len(meters),
        "wrong_dpt": bad,
        "suggested_energy_dpts": _ENERGY_DPT,
        "scaffold": scaffold,
        "note": "Energy GAs should use 13.x (energy) / 14.056 (power) so Home Assistant's "
                "energy dashboard can aggregate them. Scaffold is a suggested per-circuit / "
                "PV / battery / EVSE structure to add in ETS.",
    }


# --------------------------------------------------------------------------- #
# B4 — test / functional-acceptance protocol
# --------------------------------------------------------------------------- #
def test_protocol(project: LoadedProject) -> dict[str, Any]:
    """Per-function acceptance checklist (command -> expected status) as Markdown rows."""
    stats = _status_gas(project)
    rows = []
    for ga in _functional_commands(project):
        st = find_status(ga, [s for s in stats if s.main == ga.main]) or find_status(ga, stats)
        rows.append({
            "function": ga.name, "command": ga.address, "dpt": ga.dpt,
            "status": st.address if st else "—",
            "expected": "status reflects command within ~2 s",
        })
    md = ["# Functional acceptance protocol\n",
          "| Function | Command | DPT | Status GA | Expected | Pass | Sign-off |",
          "|---|---|---|---|---|---|---|"]
    for r in rows[:2000]:
        md.append(f"| {r['function']} | `{r['command']}` | {r['dpt'] or '?'} | "
                  f"`{r['status']}` | {r['expected']} | ☐ | |")
    md.append("\n_Execution is manual/on-site: trigger each command, verify the status GA "
              "updates. This tool drafts the checklist; it performs no bus operations._")
    return {"functions": len(rows), "markdown": "\n".join(md), "rows": rows[:2000]}


# --------------------------------------------------------------------------- #
# C2 — naming suggestions (heuristic; deep AI naming is the caller's job)
# --------------------------------------------------------------------------- #
_STATUS_WORDS = ("статус", "status", "rückmeldung", "rueck", "feedback", "state")


def suggest_naming(project: LoadedProject) -> dict[str, Any]:
    """Propose name fixes: empty names, and status GAs missing a status keyword."""
    suggestions = []
    for ga in project.gas.values():
        if ga.intent != INTENT_FUNCTIONAL:
            continue
        low = ga.name.lower()
        if not ga.name.strip():
            suggestions.append({"address": ga.address, "issue": "empty_name",
                                "suggest": "add a zone + function name so pairing/voice work"})
        elif ga.kind == "status" and not any(w in low for w in _STATUS_WORDS):
            suggestions.append({"address": ga.address, "name": ga.name, "issue": "status_no_keyword",
                                "suggest": f"{ga.name} (статус)",
                                "why": "a status keyword lets the engine pair feedback to its command"})
    return {
        "count": len(suggestions),
        "suggestions": suggestions[:500],
        "note": "Heuristic naming hygiene. Full AI naming (propose zone+function per device, "
                "3-level placement) is done by the calling assistant using the project's "
                "device/room context — this tool surfaces the mechanical fixes.",
    }
