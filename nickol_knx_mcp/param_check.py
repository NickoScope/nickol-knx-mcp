"""Cross-device parameter consistency — find the device whose ETS parameter
settings differ from its N identical siblings (the odd thermostat/sensor out).

Reads per-device ``ParameterInstanceRef`` values straight from the ``.knxproj``
project part (``P-*/0.xml``) — data that xknxproject does not expose — groups
devices by their application program (identical devices share the same
``Hardware2ProgramRefId``), and reports two kinds of finding:

  * ``clear_outlier`` — a strong majority value with a small minority
    (likely a configuration mistake: 19 thermostats at 0.5 K, one at 1.0 K);
  * ``split_config``  — the group splits into 2+ balanced variants (probably
    two zones/roles — surfaced for review, NOT an error).

Parameter RefIds are resolved to human names from the device application
program (``ParameterRef`` → ``Parameter.Name``); module-definition parameters
that don't resolve keep a readable fallback and are counted honestly.

Read-only; no ETS, no bus. A password-protected ``.knxproj`` is encrypted and
cannot be read.
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from typing import Any, Optional

_NUMERIC_RE = re.compile(r"^-?\d+$")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _app_of(refid: str) -> Optional[str]:
    m = re.match(r"(M-[0-9A-Za-z]+)_(A-[0-9A-Za-z-]+?)_", refid)
    return f"{m.group(1)}_{m.group(2)}" if m else None


def _resolve_names(zf: zipfile.ZipFile, refids: set[str]) -> dict[str, str]:
    """RefId -> human parameter name, best-effort from the application program."""
    by_app: dict[str, set[str]] = defaultdict(set)
    for r in refids:
        app = _app_of(r)
        if app:
            by_app[app].add(r)
    out: dict[str, str] = {}
    for app, rids in by_app.items():
        cand = [n for n in zf.namelist() if n.endswith(f"{app}.xml")]
        if not cand:
            continue
        try:
            axml = ET.fromstring(zf.read(cand[0]))
        except Exception:
            continue
        pref: dict[str, str] = {}
        pname: dict[str, str] = {}
        for e in axml.iter():
            ln = _localname(e.tag)
            if ln == "ParameterRef":
                pref[e.get("Id", "")] = e.get("RefId", "")
            elif ln == "Parameter":
                pname[e.get("Id", "")] = e.get("Name") or e.get("Text") or ""
        for r in rids:
            nm = pname.get(pref.get(r, ""), "")
            if nm:
                out[r] = nm
    return out


def check_device_parameters(path: str, password: Optional[str] = None,
                            min_group: int = 3, majority: float = 0.70,
                            minority_frac: float = 0.25,
                            max_findings: int = 40) -> dict[str, Any]:
    """Find parameter outliers across identical devices in a `.knxproj`.

    Returns clear outliers (a device whose value differs from its siblings) and
    balanced split-configs (review), with resolved parameter names.
    """
    try:
        zf = zipfile.ZipFile(path)
    except Exception as e:  # noqa: BLE001
        return {"error": f"cannot open .knxproj: {e}"}

    proj0 = [n for n in zf.namelist() if re.match(r"P-[^/]+/0\.xml$", n)]
    if not proj0:
        return {"error": "no P-*/0.xml (project part) found in archive"}
    try:
        root = ET.fromstring(zf.read(proj0[0]))
    except ET.ParseError:
        return {"error": "project part is not plain XML — the .knxproj is likely "
                         "password-protected/encrypted; parameters cannot be read."}

    # devices -> group by app-program, collect {param_refid: value}
    devices: list[dict[str, Any]] = []
    for el in root.iter():
        if _localname(el.tag) != "DeviceInstance":
            continue
        hp = el.get("Hardware2ProgramRefId")
        if not hp:
            continue
        params = {s.get("RefId"): s.get("Value")
                  for s in el.iter() if _localname(s.tag) == "ParameterInstanceRef"
                  and s.get("RefId") and s.get("Value") is not None}
        devices.append({
            "group": hp,
            "product": (el.get("ProductRefId") or "").split("_P-")[-1] or hp,
            "addr": el.get("Address") or "?",
            "name": el.get("Name") or "",
            "params": params,
        })

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in devices:
        groups[d["group"]].append(d)

    clear: list[dict[str, Any]] = []
    splits: list[dict[str, Any]] = []
    refids_needed: set[str] = set()

    for gkey, devs in groups.items():
        if len(devs) < min_group:
            continue
        all_rids: set[str] = set().union(*(set(d["params"]) for d in devs)) if devs else set()
        for rid in all_rids:
            present = [(d, d["params"][rid]) for d in devs if rid in d["params"]]
            if len(present) < min_group:
                continue
            counter = Counter(v for _, v in present)
            if len(counter) == 1:
                continue
            (maj_val, maj_n), = counter.most_common(1)
            minority = [(d, v) for d, v in present if v != maj_val]
            product = present[0][0]["product"]
            numeric = _NUMERIC_RE.match(maj_val) is not None
            rec = {
                "group_product": product, "refid": rid, "numeric": numeric,
                "total": len(present), "majority_value": maj_val,
            }
            if maj_n / len(present) >= majority and len(minority) <= max(1, int(len(present) * minority_frac)):
                refids_needed.add(rid)
                rec["odd_devices"] = [{"address": d["addr"], "name": d["name"], "value": v}
                                      for d, v in minority]
                clear.append(rec)
            elif len(counter) >= 2:
                refids_needed.add(rid)
                rec["variants"] = [{"value": v, "count": c} for v, c in counter.most_common()]
                splits.append(rec)

    names = _resolve_names(zf, refids_needed)

    def _decorate(rec: dict[str, Any]) -> dict[str, Any]:
        rec["parameter"] = names.get(rec["refid"], rec["refid"])
        rec["name_resolved"] = rec["refid"] in names
        return rec

    # numeric config outliers first (time/setpoint/hysteresis-like), then the rest
    clear = [_decorate(r) for r in clear]
    splits = [_decorate(r) for r in splits]
    clear.sort(key=lambda r: (not r["numeric"], len(r["odd_devices"]), -r["total"]))
    splits.sort(key=lambda r: (not r["numeric"], -r["total"]))

    grp_sizes = sorted((len(v) for v in groups.values() if len(v) >= min_group), reverse=True)
    return {
        "devices": len(devices),
        "identical_device_groups": len(grp_sizes),
        "largest_groups": grp_sizes[:8],
        "clear_outliers_count": len(clear),
        "split_configs_count": len(splits),
        "clear_outliers": clear[:max_findings],
        "split_configs": splits[:max_findings],
        "names_unresolved": sum(1 for r in (clear + splits) if not r["name_resolved"]),
        "note": "clear_outliers = a device whose value differs from its N identical "
                "siblings (likely a mistake). split_configs = the group splits into "
                "balanced variants (review — often two zones/roles, not an error). "
                "Numeric config parameters (times/setpoints/hysteresis) are listed first. "
                "Read-only; parameter values come from P-*/0.xml (xknxproject does not "
                "expose them). Some module-definition parameter names may stay as RefIds.",
    }
