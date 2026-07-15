"""Provenance / confidence for a single group address — "why did the tool decide this?".

External reviewers (twice) and a field integrator all asked for the same thing: the
enriched model mixes ETS facts, DPT-derived structure, and name heuristics, and the
downstream tools treat the result almost like a fact. This module makes the reasoning
**explicit and auditable** for one GA, without changing the core model: it replays the
same primitives and reports, per decision, the signals that fired and a confidence tier:

  * ``authoritative`` — an ETS Function role (the project author's own tagging);
  * ``structural``    — the KNX DPT (a typed, deterministic signal);
  * ``heuristic``     — a name keyword (language- and school-dependent, may mislead);
  * ``none`` / ``low`` — insufficient signal.

It also shows how a status was (or wasn't) paired and flags **conflicts** — e.g. a GA
classified ``lighting`` by DPT while its name says "AC" — which is exactly where silent
misclassification hides.
"""
from __future__ import annotations

from typing import Any, Optional

from .project import (LoadedProject, _override_kind_by_name, _domain_from_text,
                      _SOFT_DPT)
from .dpt_map import classify_dpt, is_exact_dpt
from .intent import classify_intent
from .pairing import (function_status_pairs, find_status, positional_status,
                      self_reporting, base_tokens)


def explain_ga(project: LoadedProject, address: str) -> dict[str, Any]:
    """Return the evidence and confidence behind one GA's classification + pairing."""
    ga = project.gas.get(address)
    if ga is None:
        return {"error": f"no group address {address} in the loaded project"}

    base = classify_dpt(ga.dpt_main, ga.dpt_sub)

    # --- category: the FINAL resolved domain (name > strong DPT > range context),
    # as stored on the record; here we surface the signals behind it. ---
    refined_cat = ga.category
    dpt_cat = base["category"]
    name_dom = _domain_from_text(ga.name)
    range_dom = _domain_from_text(f"{ga.main_name} {ga.middle_name}")
    soft = ((ga.dpt_main, ga.dpt_sub) in _SOFT_DPT or dpt_cat == "unknown"
            or not is_exact_dpt(ga.dpt_main, ga.dpt_sub))
    cat_ev: list[dict[str, str]] = []
    if ga.dpt_main is not None:
        cat_ev.append({"signal": f"DPT {ga.dpt or ga.dpt_main} → {dpt_cat}"
                                 + (" (domain-agnostic default)" if soft else ""),
                       "tier": "structural"})
    if name_dom:
        cat_ev.append({"signal": f"name keyword → {name_dom}", "tier": "heuristic"})
    if range_dom and soft and not name_dom:
        cat_ev.append({"signal": f"group-range name → {range_dom}", "tier": "heuristic"})

    # --- kind: DPT vs name override ---
    refined_kind = _override_kind_by_name(ga.name, base["kind"])
    kind_ev: list[dict[str, str]] = [{"signal": f"DPT → {base['kind']}", "tier": "structural"}]
    if refined_kind != base["kind"]:
        kind_ev.append({"signal": f"name keyword → {refined_kind}", "tier": "heuristic"})

    # --- ETS Function membership (authoritative) ---
    fn_hits = []
    for fid, fn in (project.functions or {}).items():
        roles = fn.get("group_addresses", {}) or {}
        for gaddr, ref in roles.items():
            if ref.get("address", gaddr) == address:
                fn_hits.append({"function": fn.get("name", fid),
                                "type": fn.get("function_type"),
                                "role": ref.get("role")})

    # --- conflict: an explicit name domain that a STRONG DPT contradicts. A soft
    # 1-bit DPT is domain-agnostic, so name winning over it is NOT a conflict (the
    # AC-on/off case is now correctly HVAC); a genuine conflict is e.g. a
    # temperature DPT named "blind", which the classifier resolves to 'unknown'. ---
    conflicts = []
    if name_dom and not soft and name_dom != dpt_cat:
        conflicts.append(
            f"name suggests '{name_dom}' but the DPT ({ga.dpt or ga.dpt_main}) strongly "
            f"encodes '{dpt_cat}' — contradictory, so the domain is left '{refined_cat}'")

    # --- status pairing: which strategy, if any ---
    fpairs = function_status_pairs(project)
    pairing: dict[str, Any] = {"paired": False, "method": "none"}
    if address in fpairs:
        pairing = {"paired": True, "method": "ets_function_role", "status": fpairs[address],
                   "tier": "authoritative"}
    elif ga.kind == "command":
        cand = [g for g in project.gas.values()
                if (g.kind == "status" or "status" in (g.name or "").lower())]
        m = find_status(ga, [c for c in cand if c.main == ga.main]) or find_status(ga, cand)
        if m is not None:
            pairing = {"paired": True, "method": "name_token", "status": m.address,
                       "tier": "heuristic"}
        elif positional_status(ga, project) is not None:
            pairing = {"paired": True, "method": "positional", "tier": "structural"}
        elif self_reporting(ga, project):
            pairing = {"paired": True, "method": "self_reporting_R+T", "tier": "structural"}

    # top confidence for the DOMAIN classification. A name/DPT conflict dominates:
    # the classification is contested regardless of any ETS-Function pairing signal.
    if conflicts:
        confidence = "contested"
    elif fn_hits:
        confidence = "authoritative"
    elif refined_cat == "unknown":
        confidence = "low"
    elif name_dom or (range_dom and soft):
        confidence = "heuristic"   # name/range decided the domain
    elif ga.dpt_main is not None:
        confidence = "structural"  # a strong DPT decided it
    else:
        confidence = "low"

    return {
        "address": address, "name": ga.name, "dpt": ga.dpt or None,
        "raw_facts": {"co_ids": ga.co_ids, "data_secure": ga.data_secure,
                      "identity_tokens": sorted(base_tokens(ga.name))},
        "category": {"value": refined_cat, "evidence": cat_ev},
        "kind": {"value": refined_kind, "evidence": kind_ev},
        "intent": {"value": classify_intent(ga.name), "tier": "heuristic (name-based)"},
        "ets_functions": fn_hits or "none — no ETS Function tags this GA (heuristics only)",
        "status_pairing": pairing,
        "conflicts": conflicts or "none",
        "confidence": confidence,
        "note": "Evidence tiers: authoritative (ETS Function role) > structural (DPT) > "
                "heuristic (name keyword). A conflict means the name and the DPT disagree — "
                "review before trusting the classification or generating an entity from it.",
    }
