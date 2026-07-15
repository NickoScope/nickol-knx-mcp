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

from .project import LoadedProject, _refine_category, _override_kind_by_name
from .dpt_map import classify_dpt
from .intent import classify_intent
from .pairing import (function_status_pairs, find_status, positional_status,
                      self_reporting, base_tokens)


def explain_ga(project: LoadedProject, address: str) -> dict[str, Any]:
    """Return the evidence and confidence behind one GA's classification + pairing."""
    ga = project.gas.get(address)
    if ga is None:
        return {"error": f"no group address {address} in the loaded project"}

    base = classify_dpt(ga.dpt_main, ga.dpt_sub)

    # --- category: DPT (structural) vs name refine (heuristic) ---
    refined_cat = _refine_category(ga.name, base["category"])
    cat_ev: list[dict[str, str]] = []
    if ga.dpt_main is not None:
        cat_ev.append({"signal": f"DPT {ga.dpt or ga.dpt_main} → {base['category']}",
                       "tier": "structural"})
    if refined_cat != base["category"]:
        cat_ev.append({"signal": f"name resolved ambiguous DPT → {refined_cat}",
                       "tier": "heuristic"})

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

    # --- conflict: DPT-domain vs name-domain (the silent-misclassification hotspot) ---
    conflicts = []
    low = (ga.name or "").lower()
    _NAME_DOMAIN = {"hvac": ("ac", " a/c", "climate", "heat", "cool", "hvac", "конд", "клима",
                             "отоплен", "температур"),
                    "shutter": ("blind", "shutter", "cover", "жалюзи", "штор", "ролл"),
                    "energy": ("meter", "energy", "power", "счётчик", "энерг", "мощност")}
    for dom, toks in _NAME_DOMAIN.items():
        if any(t in low for t in toks) and refined_cat != dom and refined_cat != "unknown":
            conflicts.append(
                f"name suggests '{dom}' but classified '{refined_cat}' (DPT took precedence "
                "over the name)")

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
    elif ga.dpt_main is not None and refined_cat != "unknown":
        confidence = "heuristic" if refined_cat != base["category"] else "structural"
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
