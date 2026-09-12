"""Corpus guard — the regression gate the public CI cannot be.

Every real bug this project has had (#11 cover pairing, #12 RM/Rückmeldung, #13 policy
profile) came from a real ETS file. Those files are confidential friends' projects and must
never reach a GitHub runner, so the public CI only ever sees synthetic fixtures. This script
closes that gap locally: it runs the whole pipeline over the real corpus, records a small set
of NUMBERS, and fails when they drift from the recorded baseline.

What leaves the machine: nothing. What goes into git: only the numbers in
``tools/corpus_baseline.json`` — counts and percentages, no addresses, no names, no paths
beyond a short label the owner chooses.

    python tools/corpus_check.py                 # check against the baseline
    python tools/corpus_check.py --update        # re-record the baseline (after a deliberate change)
    python tools/corpus_check.py --tolerance 2   # allow ±2 % drift per metric (default 0 for counts)

Exit code 1 on drift, so it can be wired into a pre-commit hook or a nightly job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from xknxproject import XKNXProj

from nickol_knx_mcp.project import build_loaded_from_raw
from nickol_knx_mcp.analyze import (validate_naming, detect_missing_status, detect_dpt_issues,
                                    detect_topology_issues, detect_role_completeness)
from nickol_knx_mcp.generate_ha import generate_ha_yaml
from nickol_knx_mcp.suggest import suggest_entities

# Corpus lives outside the package and outside git. Labels are deliberate: a label never
# reveals a client, and the baseline file carries labels only.
CORPUS_DIR = Path(__file__).resolve().parents[2] / "demo-home-for-friend"
# The corpus map lives in tools/corpus_map.json, which is gitignored: real project paths carry
# client names and must never enter the repository. See tools/corpus_map.example.json.
# Override the corpus root with NICKOL_KNX_CORPUS_DIR.
CORPUS_MAP = Path(__file__).resolve().parent / "corpus_map.json"


def _load_corpus() -> list[tuple[str, str]]:
    env_dir = os.environ.get("NICKOL_KNX_CORPUS_DIR")
    if env_dir:
        globals()["CORPUS_DIR"] = Path(env_dir).expanduser()
    if not CORPUS_MAP.exists():
        print("no corpus map: copy tools/corpus_map.example.json -> tools/corpus_map.json "
              "and point it at local .knxproj files")
        raise SystemExit(2)
    data = json.loads(CORPUS_MAP.read_text())
    return [(e["label"], e["path"]) for e in data["projects"]]


CORPUS: list[tuple[str, str]] = _load_corpus()
BASELINE = Path(__file__).resolve().parent / "corpus_baseline.json"


def _metrics(path: Path) -> dict[str, Any]:
    raw = XKNXProj(str(path)).parse()
    proj = build_loaded_from_raw(raw, str(path))

    findings: list[dict[str, Any]] = []
    for check in (validate_naming, detect_missing_status, detect_dpt_issues,
                  detect_topology_issues, detect_role_completeness):
        findings.extend(check(proj) or [])
    sev: dict[str, int] = {}
    codes: dict[str, int] = {}
    for f in findings:
        sev[f.get("severity", "?")] = sev.get(f.get("severity", "?"), 0) + 1
        codes[f.get("code", "?")] = codes.get(f.get("code", "?"), 0) + 1

    ha = generate_ha_yaml(proj)
    doc = yaml.safe_load(ha["yaml"]) or {}
    knx = doc.get("knx") or {}
    entities = {k: len(v) for k, v in knx.items() if isinstance(v, list)}

    sug = suggest_entities(raw, fallback=False)
    plat: dict[str, int] = {}
    for s in sug["suggestions"]:
        p = s["platform_options"][0]
        plat[p] = plat.get(p, 0) + 1

    cats: dict[str, int] = {}
    for ga in proj.gas.values():
        cats[ga.category] = cats.get(ga.category, 0) + 1

    return {
        "group_addresses": len(proj.gas),
        "devices": len(proj.devices),
        "categories": dict(sorted(cats.items())),
        "findings_by_severity": dict(sorted(sev.items())),
        "findings_by_code": dict(sorted(codes.items())),
        "ha_entities": dict(sorted(entities.items())),
        "ha_review_items": len(ha.get("review") or []),
        "suggestions_by_platform": dict(sorted(plat.items())),
        "suggestion_hints": {k: v for k, v in sug["hints"].items() if k != "state"},
    }


def _flat(d: dict[str, Any], prefix: str = "") -> dict[str, int]:
    out: dict[str, int] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        elif isinstance(v, (int, float)):
            out[key] = v
    return out


def _compare(label: str, base: dict, now: dict, tol: float) -> list[str]:
    a, b = _flat(base), _flat(now)
    drift = []
    for key in sorted(set(a) | set(b)):
        old, new = a.get(key), b.get(key)
        if old == new:
            continue
        if old is None:
            drift.append(f"{label}: NEW {key} = {new}")
        elif new is None:
            drift.append(f"{label}: GONE {key} (was {old})")
        else:
            delta = abs(new - old)
            allowed = max(0.0, old * tol / 100.0)
            if delta > allowed:
                drift.append(f"{label}: {key} {old} -> {new} ({new - old:+d})")
    return drift


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="re-record the baseline")
    ap.add_argument("--tolerance", type=float, default=0.0, help="allowed drift per metric, %%")
    args = ap.parse_args()

    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {"projects": {}}
    result: dict[str, Any] = {"projects": {}}
    drift: list[str] = []
    missing: list[str] = []

    for label, rel in CORPUS:
        path = CORPUS_DIR / rel
        if not path.exists():
            missing.append(label)
            continue
        m = _metrics(path)
        # a digest of the file identifies "the same file", without storing its name or content
        m["file_digest"] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        result["projects"][label] = m
        old = baseline["projects"].get(label)
        if old is None:
            drift.append(f"{label}: no baseline yet")
            continue
        if old.get("file_digest") != m["file_digest"]:
            drift.append(f"{label}: the .knxproj itself changed — re-record with --update if intended")
            continue
        drift.extend(_compare(label, {k: v for k, v in old.items() if k != "file_digest"},
                              {k: v for k, v in m.items() if k != "file_digest"}, args.tolerance))

    for label in missing:
        print(f"skip {label}: file not present on this machine")

    if args.update:
        BASELINE.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"baseline recorded for {len(result['projects'])} project(s) -> {BASELINE.name}")
        return 0

    if drift:
        print(f"\nCORPUS DRIFT — {len(drift)} metric(s) moved:\n")
        for line in drift:
            print("  " + line)
        print("\nIf the change is deliberate, re-record: python tools/corpus_check.py --update")
        return 1

    print(f"corpus OK — {len(result['projects'])} project(s), no drift against the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
