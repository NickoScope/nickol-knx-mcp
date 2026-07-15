"""Project Policy Profile — validate a project against *its own* agreed rules,
not one universal "professional standard".

Integrators disagree on conventions (main-group taxonomy, naming, which
functions need a status). A hardcoded methodology then "cries wolf" on a project
that is perfectly correct by its own school. This module lets a project ship a
small **policy profile** (YAML) that says what *this* project's rules are, and
checks conformance against it:

  * ``main_groups``  — which functional domain each main group is meant to hold
    (a shutter GA sitting in the lighting range is flagged);
  * ``naming``       — a regex names must match, and the status suffix;
  * ``pairing``      — which categories require a status and which are exempt
    (surfaced so the missing-status view can honour the project's own policy);
  * ``reserve``      — expect a reserve range.

With no profile, ``DEFAULT_POLICY`` encodes the CLAUDE.md methodology as a
*starting* profile — but it is a default to override, not a law. Report-only.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Optional

from .project import LoadedProject
from .intent import INTENT_FUNCTIONAL
from .analyze import _is_central_macro

# Categories whose placement a main-group taxonomy actually constrains. Sensors,
# diagnostics, scene links and metering are cross-cutting — they legitimately
# appear inside any actuator domain's main group — so only these are checked.
_ACTUATOR_DOMAINS = {"lighting", "shutter", "hvac"}

# The CLAUDE.md taxonomy, expressed as an overridable default profile.
DEFAULT_POLICY: dict[str, Any] = {
    "name": "default (CLAUDE.md methodology — override per project)",
    "main_groups": {
        0: ["central", "scene"],
        1: ["lighting"],
        2: ["shutter"],
        3: ["hvac"],
        4: ["sensor"],
        5: ["energy"],
        6: ["diagnostics"],
        7: ["reserve"],
    },
    "naming": {"regex": None, "status_suffix": "Status"},
    "pairing": {
        "require_status_for": ["lighting", "shutter", "hvac"],
        "exempt": ["scene", "sensor", "central", "diagnostics", "energy"],
    },
    "reserve": {"expect_range": True},
}


def load_policy(path: Optional[str] = None) -> dict[str, Any]:
    """Load a policy profile (YAML) merged over the defaults; None -> defaults.

    A loaded file is tagged ``_source="profile"`` (its declared taxonomy is
    authoritative); with no file the taxonomy is later *inferred from the project
    itself* rather than imposed, so we never cry wolf against an alien standard.
    """
    if not path:
        return {**DEFAULT_POLICY, "_source": "default"}
    try:
        import yaml
    except Exception:  # noqa: BLE001
        return {**DEFAULT_POLICY, "_error": "PyYAML not available; using defaults"}
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as e:  # noqa: BLE001
        return {**DEFAULT_POLICY, "_error": f"cannot read profile: {e}; using defaults"}
    prof = dict(DEFAULT_POLICY)
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(prof.get(k), dict):
            prof[k] = {**prof[k], **v}
        else:
            prof[k] = v
    # normalise main_groups keys to int, values to list
    mg = {}
    for k, v in (prof.get("main_groups") or {}).items():
        try:
            mg[int(k)] = v if isinstance(v, list) else [v]
        except (ValueError, TypeError):
            continue
    prof["main_groups"] = mg
    prof["_source"] = "profile"
    return prof


def _infer_taxonomy(project: LoadedProject, min_group: int = 3,
                    min_share: float = 0.6) -> dict[int, list[str]]:
    """Infer each main group's domain from the project itself (dominant category
    with a clear majority). Mains with no clear majority are left out — we do not
    guess a taxonomy the project doesn't actually follow."""
    per_main: dict[int, Counter] = defaultdict(Counter)
    for ga in project.gas.values():
        if ga.intent != INTENT_FUNCTIONAL or ga.main is None:
            continue
        if ga.category and ga.category != "unknown":
            per_main[ga.main][ga.category] += 1
    tax: dict[int, list[str]] = {}
    for m, c in per_main.items():
        total = sum(c.values())
        dom, n = c.most_common(1)[0]
        if total >= min_group and n / total >= min_share:
            tax[m] = [dom]
    return tax


def check_policy(project: LoadedProject, policy: dict[str, Any]) -> dict[str, Any]:
    """Validate the project against the policy profile. Report-only findings.

    With a declared profile (``_source=="profile"``) the profile's main-group
    taxonomy is authoritative. With no profile the taxonomy is **inferred from the
    project itself** and we flag GAs that deviate from their main group's own
    majority domain — never against an external "standard".
    """
    findings: list[dict[str, Any]] = []
    source = policy.get("_source", "default")
    if source == "profile":
        mg = policy.get("main_groups") or {}
        code, tax_source = "policy_domain_mismatch", "declared profile"
    else:
        mg = _infer_taxonomy(project)
        code, tax_source = "policy_taxonomy_outlier", "inferred from the project"
    naming = policy.get("naming") or {}
    regex = naming.get("regex")
    pattern = re.compile(regex) if regex else None

    domain_ok = domain_bad = named_ok = named_bad = 0
    seen_mains: set[int] = set()

    for addr, ga in project.gas.items():
        if ga.intent != INTENT_FUNCTIONAL or ga.main is None:
            continue
        seen_mains.add(ga.main)
        if not (ga.name or "").strip():
            continue  # empty name -> unreliable classification; root cause is empty_name

        # 1. main-group taxonomy conformance (only when the domain is known).
        # Only ACTUATOR categories are checked: a lighting/shutter/HVAC main
        # legitimately also holds motion sensors, thresholds, timeout parameters
        # and scene links, so flagging those cross-cutting GAs as taxonomy
        # outliers is noise. A misplaced actuator (an HVAC load in the lighting
        # main) is the real signal.
        allowed = mg.get(ga.main)
        if allowed and ga.category in _ACTUATOR_DOMAINS and not _is_central_macro(ga.name):
            # central macros ("Весь свет выкл", "All blinds down") legitimately
            # live in the central/scene main — their domain is not misplacement
            if ga.category in allowed:
                domain_ok += 1
            else:
                domain_bad += 1
                where = ("this project's policy" if source == "profile"
                         else "the rest of that main group in this project")
                findings.append({
                    "severity": "warning", "code": code, "address": addr,
                    "message": f"'{ga.name}' is category '{ga.category}' but main group "
                               f"{ga.main} holds {allowed} per {where}.",
                    "name": ga.name, "main": ga.main,
                    "found": ga.category, "expected": allowed,
                })

        # 2. naming regex conformance
        if pattern:
            if pattern.search(ga.name or ""):
                named_ok += 1
            else:
                named_bad += 1
                findings.append({
                    "severity": "warning", "code": "policy_naming_mismatch", "address": addr,
                    "message": f"'{ga.name}' does not match this project's naming pattern.",
                    "name": ga.name,
                })

    # 3. reserve range expected?
    reserve_mains = [m for m, doms in mg.items() if "reserve" in doms]
    if (policy.get("reserve") or {}).get("expect_range"):
        if reserve_mains and not any(m in seen_mains for m in reserve_mains):
            findings.append({
                "severity": "info", "code": "policy_no_reserve", "address": "-",
                "message": f"Policy expects a reserve range (main {reserve_mains}) but none is "
                           "populated — leave spare address space per this project's convention.",
            })
        elif not reserve_mains and source != "profile":
            # inferred taxonomy can't see reserves (reserve GAs are non-functional
            # by intent) — before complaining, look for reserve-intent GAs and
            # reserve-named group ranges directly.
            has_reserve = any(g.intent == "reserve" for g in project.gas.values())
            if not has_reserve:
                rtok = ("резерв", "reserve", "spare")
                names = [g.main_name for g in project.gas.values()] + \
                        [g.middle_name for g in project.gas.values()]
                has_reserve = any(t in (n or "").lower() for n in names for t in rtok)
            if not has_reserve:
                findings.append({
                    "severity": "info", "code": "policy_no_reserve", "address": "-",
                    "message": "No reserve main group exists in the project — every main is "
                               "populated. Leave spare address space for future extensions.",
                })

    errors = sum(1 for f in findings if f["severity"] == "error")
    warns = sum(1 for f in findings if f["severity"] == "warning")
    return {
        "policy_name": policy.get("name"),
        "policy_error": policy.get("_error"),
        "taxonomy_source": tax_source,
        "taxonomy": {str(k): v for k, v in sorted(mg.items())} if mg else {},
        "checked_functional_gas": domain_ok + domain_bad,
        "domain_conformance": {"ok": domain_ok, "mismatch": domain_bad},
        "naming_conformance": ({"ok": named_ok, "mismatch": named_bad} if pattern
                               else "no naming regex in policy"),
        "pairing_policy": policy.get("pairing"),
        "findings_summary": {"errors": errors, "warnings": warns, "total": len(findings)},
        "findings": findings[:200],
        "note": "Conformance to THIS project's policy profile, not an abstract standard. "
                "Override the default profile with your own (main-group taxonomy, naming "
                "regex, pairing exemptions). Report-only; nothing is changed.",
    }


def example_policy_yaml() -> str:
    """A commented example profile an integrator can copy and adapt."""
    return (
        "# nickol-knx Project Policy Profile — your project's rules, not a universal standard.\n"
        "# Pass its path to check_policy(profile_path=...). Any key you omit falls back to the default.\n"
        "name: \"My project policy\"\n\n"
        "# Which functional domain each main group is meant to hold:\n"
        "main_groups:\n"
        "  0: [central, scene]\n"
        "  1: [lighting]\n"
        "  2: [shutter]\n"
        "  3: [hvac]\n"
        "  4: [sensor]\n"
        "  5: [energy]\n"
        "  6: [diagnostics]\n"
        "  7: [reserve]\n\n"
        "naming:\n"
        "  # names must match this regex (omit to skip); e.g. Zone_Function_Role:\n"
        "  regex: null\n"
        "  status_suffix: Status\n\n"
        "pairing:\n"
        "  require_status_for: [lighting, shutter, hvac]\n"
        "  exempt: [scene, sensor, central, diagnostics, energy]\n\n"
        "reserve:\n"
        "  expect_range: true\n"
    )
