"""Validation and analysis passes over a LoadedProject.

Three independent checks, each returning a list of structured findings:
  * validate_naming        - 3-level structure, empty/duplicate names, missing DPT
  * detect_missing_status  - command GAs lacking a status/feedback counterpart
  * detect_dpt_issues      - missing, inconsistent or mismatched DPTs

Findings are plain dicts so they serialize straight to JSON for the MCP client.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Optional

from .project import LoadedProject, GARecord, STATUS_KEYWORDS
from .pairing import find_status, function_status_pairs
from .intent import INTENT_FUNCTIONAL, INTENT_RESERVE, INTENT_SCRATCH

SEVERITY_ERROR = "error"
SEVERITY_WARN = "warning"
SEVERITY_INFO = "info"


def _finding(severity: str, code: str, address: str, message: str,
             **extra: Any) -> dict[str, Any]:
    f = {"severity": severity, "code": code, "address": address, "message": message}
    f.update(extra)
    return f


# --------------------------------------------------------------------------- #
# Naming validation
# --------------------------------------------------------------------------- #
def validate_naming(project: LoadedProject,
                    name_regex: Optional[str] = None,
                    min_name_len: int = 3) -> list[dict[str, Any]]:
    """Check naming conventions and 3-level structure."""
    findings: list[dict[str, Any]] = []

    style = (project.style or "").lower()
    if "three" not in style:
        findings.append(_finding(
            SEVERITY_WARN, "ga_style_not_three_level", "-",
            f"Group address style is '{project.style or 'unknown'}', expected ThreeLevel. "
            "The agreed convention is a 3-level Main/Middle/Sub structure.",
        ))

    pattern = re.compile(name_regex) if name_regex else None
    seen_names: dict[str, list[str]] = defaultdict(list)

    for addr, ga in project.gas.items():
        name = ga.name.strip()
        if not name:
            findings.append(_finding(
                SEVERITY_ERROR, "empty_name", addr,
                "Group address has no name.",
            ))
            continue

        # Reserve / logic / scratch GAs are intentional placeholders — short
        # names, repeated "Резерв", non-conventional names are expected, so they
        # must not raise naming warnings (that is the noise we are removing).
        if ga.intent != INTENT_FUNCTIONAL:
            continue

        seen_names[name.lower()].append(addr)

        if len(name) < min_name_len:
            findings.append(_finding(
                SEVERITY_WARN, "name_too_short", addr,
                f"Name '{name}' is shorter than {min_name_len} characters.",
                name=name,
            ))

        if pattern and not pattern.search(name):
            findings.append(_finding(
                SEVERITY_WARN, "name_pattern_mismatch", addr,
                f"Name '{name}' does not match the required pattern.",
                name=name,
            ))

        if ga.main is None:
            findings.append(_finding(
                SEVERITY_WARN, "not_three_level_address", addr,
                f"Address '{addr}' is not a 3-level address.",
            ))

    for low, addrs in seen_names.items():
        if len(addrs) > 1:
            findings.append(_finding(
                SEVERITY_WARN, "duplicate_name", ", ".join(addrs),
                f"Name used by {len(addrs)} group addresses: {addrs}.",
                addresses=addrs,
            ))

    # Main-group names present?
    main_named: dict[int, str] = {}
    for ga in project.gas.values():
        if ga.main is not None and ga.main not in main_named:
            main_named[ga.main] = ga.main_name
    for main, mname in sorted(main_named.items()):
        if not mname:
            findings.append(_finding(
                SEVERITY_INFO, "main_group_unnamed", f"{main}/-/-",
                f"Main group {main} has no descriptive name.",
            ))

    return findings


# --------------------------------------------------------------------------- #
# Missing status detection
# --------------------------------------------------------------------------- #
def _function_role_status(project: LoadedProject) -> list[dict[str, Any]]:
    """Use ETS Functions (GA roles) as the primary signal.

    A function that has at least one command-role GA but no status/info-role GA
    is flagged. Role strings vary by manufacturer, so we match generously.
    """
    findings: list[dict[str, Any]] = []
    status_tokens = ("info", "status", "state", "feedback", "rueck", "rück")
    for fid, fn in project.functions.items():
        roles = fn.get("group_addresses", {}) or {}
        if not roles:
            continue
        has_command = False
        has_status = False
        cmd_addrs: list[str] = []
        for ga_addr, ref in roles.items():
            role = (ref.get("role") or "").lower()
            addr = ref.get("address", ga_addr)
            if any(t in role for t in status_tokens):
                has_status = True
            else:
                # treat non-status roles that look writable as commands
                has_command = True
                cmd_addrs.append(addr)
        if has_command and not has_status:
            findings.append(_finding(
                SEVERITY_WARN, "function_missing_status",
                ", ".join(cmd_addrs) or "-",
                f"Function '{fn.get('name', fid)}' ({fn.get('function_type', '?')}) "
                "has command GAs but no status/feedback GA.",
                function=fn.get("name", fid),
                addresses=cmd_addrs,
            ))
    return findings


def _is_status_ga(ga: GARecord) -> bool:
    if ga.kind == "status":
        return True
    low = ga.name.lower()
    return any(k in low for k in STATUS_KEYWORDS)


# command DPT main -> acceptable status DPT mains
_STATUS_COMPAT = {
    1: {1},            # switch command -> 1.x status
    3: {1, 5},         # relative dim -> on/off or brightness status
    5: {5},            # scaling setpoint -> scaling status
    9: {9},            # float setpoint -> float status
}


def detect_missing_status(project: LoadedProject) -> list[dict[str, Any]]:
    """Detect controllable GAs that lack a status counterpart.

    Strategy:
      1. ETS Functions roles (authoritative when present).
      2. Heuristic per middle-group sibling search for command GAs not covered
         by any function.
    """
    findings = _function_role_status(project)

    # Commands already paired to a status by an ETS Function are satisfied
    # (authoritative). Plus any address a function-missing-status finding covers.
    covered: set[str] = set(function_status_pairs(project).keys())
    for f in findings:
        covered.update(f.get("addresses", []))

    # All status-like GAs become pairing candidates (project-wide).
    status_gas = [ga for ga in project.gas.values() if _is_status_ga(ga)]

    for addr, ga in project.gas.items():
        if addr in covered:
            continue
        if ga.intent != INTENT_FUNCTIONAL:
            continue  # reserve / logic / scratch GAs need no status by design
        if ga.kind != "command":
            continue
        if ga.dpt_main is None:
            continue  # DPT issue handled elsewhere
        # prefer same-main-group candidates, fall back to whole project
        same_main = [s for s in status_gas if s.main == ga.main]
        match = find_status(ga, same_main) or find_status(ga, status_gas)
        if match is None:
            findings.append(_finding(
                SEVERITY_WARN, "missing_status_address", addr,
                f"Command '{ga.name}' (DPT {ga.dpt or '?'}, {ga.label}) has no "
                "status/feedback GA. Home Assistant cannot read real state.",
                name=ga.name, dpt=ga.dpt, category=ga.category,
            ))

    return findings


# --------------------------------------------------------------------------- #
# DPT consistency
# --------------------------------------------------------------------------- #
def detect_dpt_issues(project: LoadedProject) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    # 1. missing DPT
    for addr, ga in project.gas.items():
        if ga.dpt_main is None:
            # A reserve / scratch GA with no DPT is intentional (a spare), so it
            # is an INFO note, not a 🔴 error that blocks the project.
            if ga.intent in (INTENT_RESERVE, INTENT_SCRATCH):
                findings.append(_finding(
                    SEVERITY_INFO, "reserve_without_dpt", addr,
                    f"'{ga.name}' is a {ga.intent} placeholder with no DPT — "
                    "intentional, assign a DPT only when you start using it.",
                    name=ga.name, intent=ga.intent,
                ))
            else:
                findings.append(_finding(
                    SEVERITY_ERROR, "missing_dpt", addr,
                    f"'{ga.name}' has no DPT assigned. Home Assistant requires a DPT "
                    "to decode this group address.",
                    name=ga.name,
                ))

    # 2. CO <-> GA dpt mismatch
    cos = project.raw.get("communication_objects", {})
    for addr, ga in project.gas.items():
        if ga.dpt_main is None:
            continue
        for co_id in ga.co_ids:
            co = cos.get(co_id)
            if not co:
                continue
            co_dpts = co.get("dpts") or []
            if not co_dpts:
                continue
            mains = {d.get("main") for d in co_dpts}
            if ga.dpt_main not in mains:
                findings.append(_finding(
                    SEVERITY_WARN, "dpt_mismatch_co", addr,
                    f"GA DPT main {ga.dpt_main} differs from linked communication "
                    f"object '{co.get('name','?')}' DPT main(s) {sorted(m for m in mains if m is not None)}.",
                    name=ga.name,
                ))
                break

    # 3. same normalized name, different DPT
    by_name: dict[str, list[GARecord]] = defaultdict(list)
    for ga in project.gas.values():
        if ga.name.strip():
            by_name[ga.name.strip().lower()].append(ga)
    for low, recs in by_name.items():
        # Reserve / logic / scratch GAs intentionally share a generic name
        # ("Резерв") across different DPTs — not an inconsistency.
        if recs[0].intent != INTENT_FUNCTIONAL:
            continue
        dpts = {r.dpt for r in recs if r.dpt}
        if len(dpts) > 1:
            findings.append(_finding(
                SEVERITY_WARN, "inconsistent_dpt", ", ".join(r.address for r in recs),
                f"Group addresses sharing name '{recs[0].name}' use different DPTs: "
                f"{sorted(dpts)}.",
                addresses=[r.address for r in recs], dpts=sorted(dpts),
            ))

    return findings
