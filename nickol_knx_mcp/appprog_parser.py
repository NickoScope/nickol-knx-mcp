"""Parse exact device object models from an ETS ``.knxproj`` / ``.knxprod``.

Deterministic extraction of the vendor communication-object model — the SUPERSET of
objects a device can expose — from the ``M-*/`` application programs embedded in a
``.knxproj`` (used devices) or a manufacturer ``.knxprod`` product database. The result
feeds the local device catalog that ``decompose_device`` consumes (``catalog-exact``).

Read-only, and PII-safe: it reads ONLY the manufacturer application-program XML
(``M-*/Hardware.xml`` + ``M-*/M-*_A-*.xml`` — object number / name / size / DPT / flags).
It never opens the client project (``P-*/0.xml``); group addresses, project names and
device placement are not read.

Parsing note: this reads the base ``<ComObject>`` elements, where most vendors
(Zennio, ABB, EOS, Hugo Müller) publish the full object model. A few vendors (STEINEL,
Hörmann, some Intesis) publish names/DPTs on ``<ComObjectRef>`` instead; those devices
yield object *counts* but sparser per-object detail — flagged in the coverage manifest.
"""
from __future__ import annotations

import os
import re
import zipfile
from typing import Any, Optional

_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_COMOBJ_RE = re.compile(r"<ComObject\b([^>]*?)/?>")
_COMREF_RE = re.compile(r"<ComObjectRef\b([^>]*?)/?>")
_HW_SPLIT_RE = re.compile(r"<Hardware\b")
_APPREF_RE = re.compile(r'<ApplicationProgramRef\s+RefId="([^"]+)"')
_APPVER_RE = re.compile(r'ApplicationVersion="(\d+)"')
_SIZE_RE = re.compile(r"(\d+)\s*(Bit|Byte)", re.I)
_CH_TOKEN_RE = re.compile(r"\[([A-Za-z]{1,3}\d+)\]")          # display token: [C1] [O12] [T3]
_LF_RE = re.compile(r"^\s*\[LF\]")

# KNX manufacturer id (hex in the M-code) -> vendor name (common ones; extend freely)
_MANUFACTURERS = {
    "M-0001": "Siemens", "M-0002": "ABB", "M-0008": "Insta/Gira", "M-0083": "Berker",
    "M-000C": "Merten", "M-0064": "Zennio(alt)", "M-0071": "Zennio", "M-0077": "Intesis (HMS)",
    "M-008E": "STEINEL", "M-00C5": "Ekinex", "M-00FC": "Hugo Müller", "M-01F6": "EOS",
    "M-0201": "Hörmann", "M-0083b": "Berker",
}


def _attrs(s: str) -> dict[str, str]:
    return dict(_ATTR_RE.findall(s))


def _size_bits(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    m = _SIZE_RE.search(s)
    if not m:
        return None
    n = int(m.group(1))
    return n if m.group(2).lower() == "bit" else n * 8


def _dpt(s: Optional[str]) -> Optional[str]:
    """'DPST-1-2' -> '1.002'; 'DPT-1' -> '1'; missing -> None (never guessed)."""
    if not s:
        return None
    m = re.match(r"DPST-(\d+)-(\d+)$", s)
    if m:
        return f"{int(m.group(1))}.{int(m.group(2)):03d}"
    m = re.match(r"DPT-(\d+)$", s)
    if m:
        return str(int(m.group(1)))
    return s  # unrecognised format: keep verbatim rather than drop


def _role(write: bool, transmit: bool, read: bool, name: str) -> str:
    n = (name or "").lower()
    if any(k in n for k in ("status", "(status)", "state", "rückmeldung", "статус")):
        return "status"
    if write and not transmit:
        return "cmd"
    if transmit and read and not write:
        return "status"
    if write:
        return "cmd"
    return "status" if transmit else "param"


def _channel_token(text: str, name: str) -> Optional[str]:
    """Return the repeating-block key for an object, e.g. 'C', 'O', 'T', or None (general)."""
    m = _CH_TOKEN_RE.search(text or "")
    if m:
        return re.match(r"([A-Za-z]{1,3})", m.group(1)).group(1)
    m = re.search(r"\bch\[(\d+)\]", name or "")   # internal 'oX.ch[0].y' form
    return "ch" if m else None


def _parse_comobjects(xml_text: str) -> list[dict[str, Any]]:
    """Parse the object model from base ``<ComObject>`` elements, then enrich
    from ``<ComObjectRef>``.

    Some vendors (Zennio, ABB, EOS…) publish the full model on the base
    elements; others (HDL, Ekinex, Creatrol…) leave the base as a near-empty
    stub and put names/DPTs/flags on the refs. Merging is conservative: a ref
    value only FILLS a field the base left empty, and the DPT is taken only
    when every ref of that object that declares one AGREES — refs are
    parameter-dependent variants, and a disagreeing DPT stays honestly unset
    rather than guessed.
    """
    base: dict[str, dict[str, Any]] = {}   # base Id -> raw attrs
    for m in _COMOBJ_RE.finditer(xml_text):
        a = _attrs(m.group(1))
        if "Number" in a and a.get("Id"):
            base[a["Id"]] = a
        elif "Number" in a:
            base[f"_anon{len(base)}"] = a

    refs: dict[str, list[dict[str, str]]] = {}
    for m in _COMREF_RE.finditer(xml_text):
        a = _attrs(m.group(1))
        rid = a.get("RefId")
        if rid:
            refs.setdefault(rid, []).append(a)

    def _merged(a: dict[str, str], rlist: list[dict[str, str]]) -> dict[str, str]:
        out = dict(a)
        for field in ("Text", "Name", "FunctionText", "ObjectSize",
                      "ReadFlag", "WriteFlag", "CommunicationFlag",
                      "TransmitFlag", "UpdateFlag"):
            if not out.get(field):
                vals = [r[field] for r in rlist if r.get(field)]
                if vals:
                    out[field] = vals[0]
        if not out.get("DatapointType"):
            dpts = {r["DatapointType"] for r in rlist if r.get("DatapointType")}
            if len(dpts) == 1:
                out["DatapointType"] = dpts.pop()
            elif len(dpts) > 1:
                out["_dpt_variants"] = ", ".join(sorted(dpts))
        return out

    objs: list[dict[str, Any]] = []
    for oid, a in base.items():
        a = _merged(a, refs.get(oid, []))
        w = a.get("WriteFlag", "").lower() == "enabled"
        t = a.get("TransmitFlag", "").lower() == "enabled"
        r = a.get("ReadFlag", "").lower() == "enabled"
        text = a.get("Text") or a.get("Name") or ""
        try:
            number = int(a["Number"])
        except ValueError:
            continue
        rec = {
            "number": number,
            "name": text,
            "internal_name": a.get("Name"),
            "function": a.get("FunctionText"),
            "size_bits": _size_bits(a.get("ObjectSize")),
            "dpt": _dpt(a.get("DatapointType")),
            "flags": {"C": a.get("CommunicationFlag", "").lower() == "enabled",
                      "R": r, "W": w, "T": t,
                      "U": a.get("UpdateFlag", "").lower() == "enabled"},
            "role": _role(w, t, r, text),
        }
        if a.get("_dpt_variants"):
            rec["dpt_variants"] = ", ".join(
                sorted(_dpt(x) or x for x in a["_dpt_variants"].split(", ")))
        objs.append(rec)
    objs.sort(key=lambda o: o["number"])
    return objs


def _detect_blocks(objs: list[dict[str, Any]]) -> dict[str, Any]:
    """Best-effort per-channel block/stride + general/[LF] split from object names."""
    general, lf, chan = [], [], {}
    for o in objs:
        text = o["name"] or ""
        if _LF_RE.match(text):
            lf.append(o)
            continue
        tok = _channel_token(text, o.get("internal_name") or "")
        if tok:
            chan.setdefault(tok, []).append(o)
        else:
            general.append(o)

    blocks = []
    for tok, group in chan.items():
        # instances = distinct channel indices seen in the display tokens
        idxs = sorted({int(mm.group(1)) for o in group
                       for mm in [re.search(r"\[[A-Za-z]{1,3}(\d+)\]", o["name"] or "")] if mm})
        instances = len(idxs) or 1
        per = max(1, len(group) // instances)
        nums = sorted(o["number"] for o in group)
        stride = None
        if instances > 1 and len(nums) >= per + 1:
            stride = nums[per] - nums[0]
        first = [o for o in group if re.search(rf"\[{tok}?0*1\]", o["name"] or "")] or group[:per]
        blocks.append({
            "unit": tok, "instances": instances, "objects_per_instance": per,
            "stride": stride, "first_instance_objects": first,
        })
    return {"blocks": blocks, "general_objects": general, "logic_function_objects": lf}


def _pick_app_ref(refs: list[str]) -> Optional[str]:
    """Pick the NEWEST application program by its version segment.

    ``ApplicationProgramRef`` ids look like ``M-0073_A-1105-12-ABCD`` — the third
    dash-segment is the application version in hex. Hardware entries can list
    several app versions, and the newest is NOT always the last listed (seen in
    the field: an HDL DALI gateway listing v18 before v16), so positional
    ``[-1]`` picked a stale program. Fall back to the last entry when the id
    doesn't match the expected shape.
    """
    if not refs:
        return None

    def ver(ref: str) -> int:
        m = re.match(r"M-[0-9A-Fa-f]+_A-[0-9A-Fa-f]+-([0-9A-Fa-f]+)-", ref)
        try:
            return int(m.group(1), 16) if m else -1
        except ValueError:
            return -1

    best = max(refs, key=ver)
    return best if ver(best) >= 0 else refs[-1]


def _hardware_map(xml_text: str) -> list[dict[str, Any]]:
    """From a Hardware.xml, list {order_number, name, app_refs[]} (latest app last).

    ``OrderNumber`` lives on the nested ``<Product>`` element, not on ``<Hardware>``
    (which carries ``SerialNumber``); fall back to ``SerialNumber`` if absent.
    """
    out = []
    for chunk in _HW_SPLIT_RE.split(xml_text)[1:]:
        body = chunk.split("</Hardware>")[0]
        head = _attrs(chunk[:chunk.find(">")] if ">" in chunk else chunk)
        m = re.search(r'OrderNumber="([^"]+)"', body)
        order = m.group(1) if m else head.get("SerialNumber")
        if not order:
            continue
        refs = _APPREF_RE.findall(body)
        out.append({"order_number": order, "name": head.get("Name"), "app_refs": refs})
    return out


def parse_project(path: str, password: Optional[str] = None) -> dict[str, Any]:
    """Parse device object models from a ``.knxproj``/``.knxprod`` archive.

    Returns ``{"devices": [...], "coverage": {...}}``. Each device carries its order
    number, application-program id/version, object counts, detected per-channel blocks
    and the full comm-object list. Reads only ``M-*`` manufacturer data.
    """
    if not os.path.isfile(path):
        return {"error": f"file not found: {path}", "devices": [], "coverage": {}}

    pwd = password.encode() if password else None
    devices: list[dict[str, Any]] = []
    seen_mfr, app_cache, hw_count = set(), {}, 0
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        hardware_files = [n for n in names if re.search(r"/Hardware\.xml$", n) and n.startswith("M-")]
        appfiles = {n for n in names if re.match(r"M-[0-9A-Fa-f]+/M-[0-9A-Fa-f]+_A-[^/]+\.xml$", n)}

        for hw in hardware_files:
            mcode = hw.split("/", 1)[0]
            seen_mfr.add(mcode)
            try:
                hw_xml = z.read(hw, pwd=pwd).decode("utf-8", "replace")
            except Exception:
                continue
            for entry in _hardware_map(hw_xml):
                hw_count += 1
                app_ref = _pick_app_ref(entry["app_refs"])
                app_path = f"{mcode}/{app_ref}.xml" if app_ref else None
                if not app_path or app_path not in appfiles:
                    devices.append({
                        "order_number": entry["order_number"], "name": entry["name"],
                        "manufacturer": _MANUFACTURERS.get(mcode, mcode),
                        "application_program": {"app_id": app_ref, "version": None},
                        "object_counts": {"master_catalog_total": 0},
                        "blocks": [], "comm_objects": [],
                        "note": "no application-program XML present for this order number",
                    })
                    continue
                if app_path not in app_cache:
                    xml_text = z.read(app_path, pwd=pwd).decode("utf-8", "replace")
                    ver = _APPVER_RE.search(xml_text[:8000])
                    app_cache[app_path] = (_parse_comobjects(xml_text),
                                           ver.group(1) if ver else None)
                objs, ver = app_cache[app_path]
                bd = _detect_blocks(objs)
                no_dpt = sum(1 for o in objs if o["dpt"] is None)
                devices.append({
                    "order_number": entry["order_number"], "name": entry["name"],
                    "manufacturer": _MANUFACTURERS.get(mcode, mcode),
                    "application_program": {"app_id": app_ref,
                                            "version": f"v{ver}" if ver else None},
                    "object_counts": {
                        "master_catalog_total": len(objs),
                        "general_objects": len(bd["general_objects"]),
                        "logic_function_objects": len(bd["logic_function_objects"]),
                        "objects_without_declared_dpt": no_dpt,
                    },
                    "blocks": [{k: v for k, v in b.items() if k != "first_instance_objects"}
                               | {"first_instance_objects": b["first_instance_objects"]}
                               for b in bd["blocks"]],
                    "comm_objects": objs,
                })

    total_obj = sum(d["object_counts"]["master_catalog_total"] for d in devices)
    total_nodpt = sum(d["object_counts"].get("objects_without_declared_dpt", 0) for d in devices)
    coverage = {
        "archive": os.path.basename(path),
        "manufacturers_seen": sorted(seen_mfr),
        "hardware_entries": hw_count,
        "devices_parsed": len(devices),
        "app_programs_parsed": len(app_cache),
        "objects_total": total_obj,
        "objects_without_dpt": total_nodpt,
        "note": "Object model = vendor master SUPERSET (all objects a device CAN expose); "
                "ETS parameters enable a subset per config. DPT null = vendor declared none "
                "(never guessed). Base <ComObject> only; ref-level vendors yield counts but "
                "sparser detail.",
    }
    return {"devices": devices, "coverage": coverage}


def _yaml_row(o: dict[str, Any]) -> dict[str, Any]:
    return {"number": o["number"], "name": o["name"], "function": o.get("function"),
            "size_bits": o.get("size_bits"), "dpt": o.get("dpt") or "unverified",
            "flags": o.get("flags"), "role": o.get("role")}


def summary(result: dict[str, Any]) -> dict[str, Any]:
    """Trim a parse result to a per-device summary (no full object lists) + coverage."""
    devs = []
    for d in result.get("devices", []):
        oc = d.get("object_counts", {})
        devs.append({
            "order_number": d.get("order_number"), "name": d.get("name"),
            "manufacturer": d.get("manufacturer"),
            "app_version": (d.get("application_program") or {}).get("version"),
            "master_objects": oc.get("master_catalog_total"),
            "objects_without_dpt": oc.get("objects_without_declared_dpt"),
            "blocks": [{"unit": b.get("unit"), "objects_per_instance": b.get("objects_per_instance"),
                        "instances": b.get("instances"), "stride": b.get("stride")}
                       for b in d.get("blocks", [])],
        })
    return {"coverage": result.get("coverage", {}), "devices": devs}


def to_catalog_yaml(result: dict[str, Any]) -> str:
    """Render a parse result as device-library YAML (library-schema.md), catalog-exact-ready.

    Per-channel blocks are collapsed to their first instance (+ stride); the full object
    list is not duplicated, matching the harvested-catalog convention.
    """
    import yaml
    devs = []
    for d in result.get("devices", []):
        blocks = [{"unit": b.get("unit"), "instances": b.get("instances"),
                   "objects_per_instance": b.get("objects_per_instance"),
                   "stride": b.get("stride"),
                   "objects": [_yaml_row(o) for o in b.get("first_instance_objects", [])]}
                  for b in d.get("blocks", [])]
        devs.append({
            "order_number": d.get("order_number"), "name": d.get("name"),
            "manufacturer": d.get("manufacturer"),
            "application_program": d.get("application_program"),
            "object_counts": d.get("object_counts"),
            "repeating_blocks": blocks,
        })
    top = {
        "schema_version": "0.1",
        "manufacturer": "(multiple — see per-device)",
        "source_note": "Parsed from ETS application programs by parse_devices_from_project. "
                       "Master catalog SUPERSET; DPT 'unverified' = vendor declared none. "
                       "No client project (P-*/0.xml) data.",
        "devices": devs,
    }
    return yaml.safe_dump(top, allow_unicode=True, sort_keys=False, width=100)
