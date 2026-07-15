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
from .pairing import (find_status, function_status_pairs, base_tokens,
                      positional_status, self_reporting)
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

    # Main-group names present? Read them from the project's GroupRanges — the
    # authoritative source. GARecord.main_name from the parser can carry a
    # MIDDLE range's name instead of the main's (first-seen shadowing), which
    # both hid truly unnamed mains and mislabeled named ones.
    main_named: dict[int, str] = {}
    for mkey, mrange in (project.raw.get("group_ranges") or {}).items():
        head = str(mkey).split("/")[0]
        if head.isdigit():
            main_named[int(head)] = mrange.get("name") or ""
    if not main_named:  # fallback for synthetic projects without group_ranges
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


# Central / group-macro command names ("Общее освещение - Все группы", "Все
# шторы - стоп", "Групповое включение"). A broadcast that fans out to many
# actuators has no single state to read back, so a missing status is expected
# rather than a defect — surfaced as INFO, not a 🟡 warning.
_CENTRAL_MACRO_TOKENS = (
    "общее", "групповое", "все ", "всё", "central", "all groups", "all lights",
    # generic group/broadcast commands (multi-word so they don't false-match "wall")
    "all blinds", "all shutters", "all covers", "all windows", "all sockets",
    "all off", "all on", "master off", "всех ",
)


def _is_central_macro(name: str) -> bool:
    low = (name or "").lower()
    return any(t in low for t in _CENTRAL_MACRO_TOKENS)


def _is_scene(ga: GARecord) -> bool:
    """Scene-control / scene-number GAs (17.x / 18.x) have no single real state to
    read back — a missing status is expected, not a defect."""
    return ga.dpt_main in (17, 18) or ga.category == "scene"


# --------------------------------------------------------------------------- #
# Sub-DPT sanity (A1): a name implies a specific DPT sub-type. Flag when the
# main matches but the sub is wrong (9.001 temp vs 9.004 lux), or — for strong
# physical quantities — when the main itself is wrong for the named function.
# Multilingual (RU / EN / DE). Conservative: only fires on clear function tokens.
# (tokens, main, sub, strong) — strong => also flag a wrong main.
# --------------------------------------------------------------------------- #
_SUBDPT_RULES: tuple = (
    (("влажност", "humidity", "feucht"), 9, 7, True),
    (("co2", "со2", "углекисл", "kohlendioxid"), 9, 8, True),
    (("освещённост", "освещенност", "luminosity", "lux", "helligkeit ("), 9, 4, True),
    (("температур", "temperatur"), 9, 1, True),
    (("мощност", "power ", "leistung"), 14, 56, True),
    (("энерги", "energy", "energie", "квтч", "kwh"), 13, 13, True),
    (("яркост", "brightness", "значение яркости", "dimmwert", "helligkeitswert"), 5, 1, False),
    (("позици", "position", "stellung"), 5, 1, False),
)


def _expected_subdpt(name: str) -> Optional[tuple[int, int, bool]]:
    low = (name or "").lower()
    for tokens, m, s, strong in _SUBDPT_RULES:
        if any(t in low for t in tokens):
            return (m, s, strong)
    return None


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

    n_positional = n_self_report = 0
    for addr, ga in project.gas.items():
        if addr in covered:
            continue
        if ga.intent != INTENT_FUNCTIONAL:
            continue  # reserve / logic / scratch GAs need no status by design
        if not (ga.name or "").strip():
            continue  # root cause is empty_name (check_naming); classification unreliable
        if ga.kind != "command":
            continue
        if ga.dpt_main is None:
            continue  # DPT issue handled elsewhere
        # prefer same-main-group candidates, fall back to whole project
        same_main = [s for s in status_gas if s.main == ga.main]
        match = find_status(ga, same_main) or find_status(ga, status_gas)
        if match is None:
            # positional school: parallel status middle, identical name, same sub
            pos = positional_status(ga, project)
            if pos is not None:
                n_positional += 1
                continue
            # actuator's R+T status object linked to the command GA itself
            if self_reporting(ga, project):
                n_self_report += 1
                continue
            if _is_scene(ga):
                findings.append(_finding(
                    SEVERITY_INFO, "scene_no_status", addr,
                    f"Scene control '{ga.name}' (DPT {ga.dpt or '?'}) has no status GA — "
                    "expected: a scene recalls/stores a preset, it has no single state to "
                    "read back. No status is applicable.",
                    name=ga.name, dpt=ga.dpt, category=ga.category,
                ))
            elif _is_central_macro(ga.name):
                findings.append(_finding(
                    SEVERITY_INFO, "central_macro_no_status", addr,
                    f"Central/group macro '{ga.name}' has no status GA — expected "
                    "for an all-groups broadcast; there is no single state to read back.",
                    name=ga.name, dpt=ga.dpt, category=ga.category,
                ))
            else:
                findings.append(_finding(
                    SEVERITY_WARN, "missing_status_address", addr,
                    f"Command '{ga.name}' (DPT {ga.dpt or '?'}, {ga.label}) has no "
                    "status/feedback GA. Home Assistant cannot read real state.",
                    name=ga.name, dpt=ga.dpt, category=ga.category,
                ))

    if n_positional or n_self_report:
        findings.append(_finding(
            SEVERITY_INFO, "status_pairing_summary", "-",
            f"{n_positional} command(s) paired positionally (parallel status middle, "
            f"identical name) and {n_self_report} self-reporting (actuator R+T object "
            "on the command GA) — no separate status GA needed.",
        ))
    findings.extend(detect_role_completeness(project))
    return findings


# --------------------------------------------------------------------------- #
# Role-aware feedback completeness (external-review gap): "does the function have
# *a* status" is not enough — a dimmer with an on/off status but NO brightness
# status silently passes and inflates coverage. Flag a value/level COMMAND
# (brightness/position, 5.001) that has no matching value STATUS.
# --------------------------------------------------------------------------- #
# Function words stripped to get the DEVICE identity (so "Kitchen worktop LED
# brightness" doesn't borrow "Kitchen island pendants brightness status" just
# because both share "kitchen"+"brightness").
_VALUE_WORDS = (
    "brightness", "value", "level", "position", "dim", "dimming", "scaling",
    "яркост", "значени", "уровень", "позици", "диммир", "положени", "стеллунг",
)


def _device_ident(name: str) -> set[str]:
    return {t for t in base_tokens(name) if not any(w in t for w in _VALUE_WORDS)}


def detect_role_completeness(project: LoadedProject) -> list[dict[str, Any]]:
    """Flag a brightness/position COMMAND (5.001) with no matching value STATUS.

    Complements detect_missing_status (which only asks for *a* status): a dimmer
    can have an on/off status yet no brightness-level feedback, which Home Assistant
    needs to show the real level after a manual/external change.
    """
    findings: list[dict[str, Any]] = []
    val_status = [g for g in project.gas.values()
                  if g.intent == INTENT_FUNCTIONAL and g.dpt_main == 5 and g.kind == "status"]
    for addr, ga in project.gas.items():
        if ga.intent != INTENT_FUNCTIONAL or ga.kind != "command":
            continue
        if ga.dpt_main != 5 or ga.dpt_sub != 1:
            continue
        if ga.category not in ("lighting", "shutter"):
            continue
        ident = _device_ident(ga.name)
        if not ident:
            continue
        need = min(2, len(ident))
        has_status = any(s.main == ga.main and len(ident & _device_ident(s.name)) >= need
                         for s in val_status)
        if not has_status:
            what = "brightness" if ga.category == "lighting" else "position"
            findings.append(_finding(
                SEVERITY_WARN, "missing_value_status", addr,
                f"'{ga.name}' is a {what} command (DPT 5.001) but its device has no "
                f"{what} status GA — Home Assistant cannot read the actual {what} "
                "after a manual or external change (an on/off status is not enough).",
                name=ga.name, category=ga.category,
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
                co_name = (co.get("name") or "").strip()
                # Zennio Logic-Function data-entry objects ("[LF] (2-Byte) Data
                # Entry N") are intentionally type-agnostic raw containers; wiring
                # a typed GA (9.x temperature, etc.) into one is expected design,
                # not a DPT bug. Surface it as INFO instead of a 🟡 warning.
                if co_name.lower().startswith("[lf]"):
                    findings.append(_finding(
                        SEVERITY_INFO, "dpt_on_logic_object", addr,
                        f"GA DPT main {ga.dpt_main} links a type-agnostic logic-function "
                        f"object '{co_name}' (DPT main {sorted(m for m in mains if m is not None)}) "
                        "— expected for LF data-entry blocks, not a mismatch.",
                        name=ga.name,
                    ))
                    break
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

    # 4. sub-DPT sanity — the name implies a specific sub-type (A1)
    for addr, ga in project.gas.items():
        if ga.intent != INTENT_FUNCTIONAL or ga.dpt_main is None:
            continue
        exp = _expected_subdpt(ga.name)
        if exp is None:
            continue
        em, es, strong = exp
        if ga.dpt_main == em and ga.dpt_sub != es:
            findings.append(_finding(
                SEVERITY_WARN, "subdpt_suspect", addr,
                f"'{ga.name}' looks like a {em}.{es:03d} function but is DPT "
                f"{ga.dpt or f'{em}.{ga.dpt_sub}'} — expected {em}.{es:03d} so Home "
                "Assistant decodes it correctly.",
                name=ga.name, found=ga.dpt, expected=f"{em}.{es:03d}",
            ))
        elif strong and ga.dpt_main != em:
            findings.append(_finding(
                SEVERITY_WARN, "subdpt_suspect", addr,
                f"'{ga.name}' looks like a {em}.{es:03d} value but its DPT main is "
                f"{ga.dpt_main} (DPT {ga.dpt or '?'}) — expected main {em}.",
                name=ga.name, found=ga.dpt, expected=f"{em}.{es:03d}",
            ))

    # 5. relative-only dimming (A2) — a 3.007 relative dimmer with no 5.001
    #    absolute-brightness GA in the same zone: Home Assistant cannot set a level.
    abs5 = [g for g in project.gas.values() if g.dpt_main == 5]
    for addr, ga in project.gas.items():
        if ga.intent != INTENT_FUNCTIONAL or ga.dpt_main != 3:
            continue
        toks = base_tokens(ga.name)
        if not toks:
            continue
        need = min(2, len(toks))
        has_abs = any(g.main == ga.main and len(toks & base_tokens(g.name)) >= need
                      for g in abs5)
        if not has_abs:
            findings.append(_finding(
                SEVERITY_WARN, "relative_only_dimming", addr,
                f"'{ga.name}' has relative dimming (3.007) but no absolute-brightness "
                "(5.001) GA in its zone — Home Assistant cannot set a brightness level; "
                "add an absolute-brightness group address.",
                name=ga.name,
            ))

    return findings


# --------------------------------------------------------------------------- #
# KNX Secure posture + keyring handover checklist (A4).
# Report-only: this server never handles key material — it only summarises the
# per-GA Security flag and emits the ETS/HA keyring workflow as a checklist.
# --------------------------------------------------------------------------- #
def secure_posture(project: LoadedProject) -> dict[str, Any]:
    """Summarise KNX Data Secure posture and the keyring handover steps."""
    gas = [g for g in project.gas.values() if g.intent == INTENT_FUNCTIONAL]
    secured = [g for g in gas if g.data_secure]
    plain = [g for g in gas if not g.data_secure]

    # A middle group carrying BOTH secured and plaintext GAs is a posture gap:
    # a function is only as secure as its weakest address.
    by_mid: dict[tuple, dict[str, int]] = defaultdict(lambda: {"sec": 0, "plain": 0})
    for g in gas:
        if g.main is None:
            continue
        by_mid[(g.main, g.middle)]["sec" if g.data_secure else "plain"] += 1
    mixed = [{"main": k[0], "middle": k[1], "secured": v["sec"], "plaintext": v["plain"]}
             for k, v in sorted(by_mid.items()) if v["sec"] and v["plain"]]

    keyring_required = len(secured) > 0
    total = len(gas)
    pct = (100 * len(secured) // total) if total else 0

    checklist = [
        "Assign every KNX Data Secure device to a **secure** tunnel/IP endpoint in "
        "ETS (Project → Security).",
        "Export the ETS **Keyring** (`.knxkeys`): Project → Security → Export Keyring "
        "(protect it with a strong password).",
        "Import the `.knxkeys` into the reader (Home Assistant KNX integration / the "
        "IP interface) — Data Secure GAs cannot be read without it.",
        "After **any** change to a secured GA, device or the secure topology, "
        "**re-export and re-import** the keyring.",
        "Store the keyring and the project password securely; **never commit them to "
        "Git** or share them in plain text.",
    ]
    if mixed:
        checklist.insert(1, f"Review the **{len(mixed)} middle group(s) with mixed "
                            "secure/plaintext addresses** — a function is only as "
                            "secure as its weakest GA; secure the whole function or none.")

    return {
        "total_functional_gas": total,
        "secured": len(secured),
        "plaintext": len(plain),
        "secured_pct": pct,
        "keyring_required": keyring_required,
        "mixed_middle_groups": mixed,
        "secured_addresses": [{"address": g.address, "name": g.name} for g in secured[:200]],
        "checklist": checklist,
    }
