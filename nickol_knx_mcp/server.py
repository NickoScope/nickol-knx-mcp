"""nickol-knx-mcp — MCP server for design-time KNX/ETS project work.

Exposes read + analysis + generation tools over a parsed .knxproj. The server
has NO KNX/IP bus connectivity of any kind: it only reads the project archive and
writes output files into a confined workspace. It can never write to a live bus.

Run (stdio):  python -m nickol_knx_mcp.server
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from .project import load_project as load_project_file, LoadedProject
from .analyze import (validate_naming, detect_missing_status, detect_dpt_issues,
                      secure_posture)
from .generate_ha import generate_ha_yaml
from .generate_ets import generate_ets_csv, generate_ets_xml
from .report import build_report
from .handover import build_handover
from .device_library import decompose_device as _decompose_device, list_recipes
from .appprog_parser import (parse_project as _parse_project,
                             summary as _appprog_summary, to_catalog_yaml as _appprog_to_yaml)
from .repair import suggest_repairs as _suggest_repairs
from .advanced import (matter_readiness, completeness_grade, energy_scaffold,
                       test_protocol, suggest_naming)
from .diffproj import diff_projects as _diff_projects
from .iot import generate_knx_iot_turtle
from .param_check import check_device_parameters as _check_device_parameters

mcp = FastMCP("nickol-knx")

# --------------------------------------------------------------------------- #
# State + safety helpers
# --------------------------------------------------------------------------- #
_STATE: dict[str, Optional[LoadedProject]] = {"project": None}

# Output writes are confined to this directory (default: ./knx-workspace).
_WORKSPACE = Path(os.environ.get("NICKOL_KNX_WORKSPACE", "./knx-workspace")).resolve()


def _project() -> LoadedProject:
    p = _STATE["project"]
    if p is None:
        raise ValueError("No project loaded. Call load_project(path) first.")
    return p


def _safe_write(rel_or_abs_path: str, content: str) -> str:
    """Write inside the workspace only. Returns the absolute path written."""
    _WORKSPACE.mkdir(parents=True, exist_ok=True)
    target = Path(rel_or_abs_path)
    if not target.is_absolute():
        target = _WORKSPACE / target
    target = target.resolve()
    if _WORKSPACE not in target.parents and target != _WORKSPACE:
        raise ValueError(
            f"Refusing to write outside workspace {_WORKSPACE}. "
            "Set NICKOL_KNX_WORKSPACE to change it."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


# --------------------------------------------------------------------------- #
# Read tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def load_project(path: str, password: Optional[str] = None,
                 language: Optional[str] = None) -> dict[str, Any]:
    """Parse a .knxproj file (read-only) and cache it for the session.

    Args:
        path: Path to the .knxproj file.
        password: Project password, if the .knxproj is protected.
        language: Optional language code (e.g. 'de-DE', 'ru-RU').
    """
    proj = load_project_file(path, password=password, language=language)
    _STATE["project"] = proj
    return {
        "loaded": True,
        "name": proj.info.get("name"),
        "ga_style": proj.style,
        "group_addresses": len(proj.gas),
        "devices": len(proj.devices),
        "functions": len(proj.functions),
        "ets_tool_version": proj.info.get("tool_version"),
    }


@mcp.tool()
def list_group_addresses(category: Optional[str] = None,
                         kind: Optional[str] = None,
                         missing_dpt_only: bool = False,
                         limit: int = 500) -> list[dict[str, Any]]:
    """List parsed group addresses with classification.

    Filters: category (lighting/shutter/hvac/sensor/scene/energy/diagnostics),
    kind (command/status/sensor), missing_dpt_only.
    """
    proj = _project()
    out = []
    for ga in proj.gas.values():
        if category and ga.category != category:
            continue
        if kind and ga.kind != kind:
            continue
        if missing_dpt_only and ga.dpt_main is not None:
            continue
        out.append({
            "address": ga.address, "name": ga.name, "dpt": ga.dpt,
            "category": ga.category, "kind": ga.kind, "intent": ga.intent,
            "ha_platform": ga.ha_platform, "secure": ga.data_secure,
            "description": ga.description,
        })
        if len(out) >= limit:
            break
    return out


@mcp.tool()
def get_devices() -> list[dict[str, Any]]:
    """List devices: individual address, name, order number, manufacturer."""
    proj = _project()
    return [{
        "individual_address": d.get("individual_address"),
        "name": d.get("name"),
        "order_number": d.get("order_number"),
        "manufacturer": d.get("manufacturer_name"),
        "communication_objects": len(d.get("communication_object_ids", []) or []),
    } for d in proj.devices.values()]


@mcp.tool()
def get_topology() -> dict[str, Any]:
    """Return the area/line/device topology tree."""
    proj = _project()
    tree: dict[str, Any] = {}
    for aid, area in proj.topology.items():
        lines = {}
        for lid, line in area.get("lines", {}).items():
            lines[lid] = {"name": line.get("name"),
                          "medium": line.get("medium_type"),
                          "devices": line.get("devices", [])}
        tree[aid] = {"name": area.get("name"), "lines": lines}
    return tree


# --------------------------------------------------------------------------- #
# Analysis tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def check_naming(name_regex: Optional[str] = None) -> list[dict[str, Any]]:
    """Validate naming conventions and 3-level structure."""
    return validate_naming(_project(), name_regex=name_regex)


@mcp.tool()
def check_missing_status() -> list[dict[str, Any]]:
    """Detect controllable GAs lacking a status/feedback counterpart."""
    return detect_missing_status(_project())


@mcp.tool()
def check_dpt() -> list[dict[str, Any]]:
    """Detect missing, inconsistent or mismatched DPTs."""
    return detect_dpt_issues(_project())


@mcp.tool()
def suggest_repairs() -> dict[str, Any]:
    """Propose concrete fixes for the project's findings — repair, don't just flag.

    For each issue it suggests a reviewable fix: infer a DPT for a GA that has none,
    correct a suspect sub-DPT, synthesise a status/feedback GA in a free address slot,
    or add an absolute-brightness GA for a relative-only dimmer. Suggestions only —
    a human reviews them; accepted new GAs feed generate_ets_group_addresses. The
    server never writes to ETS or the bus.
    """
    return _suggest_repairs(_project())


@mcp.tool()
def check_secure() -> dict[str, Any]:
    """Summarise KNX Data Secure posture + the keyring handover checklist.

    Reports how many group addresses are secured vs plaintext, flags middle
    groups that mix secure and plaintext addresses (a function is only as secure
    as its weakest GA), and emits the ETS/HA keyring workflow as a checklist.
    Report-only — this server never touches key material.
    """
    return secure_posture(_project())


@mcp.tool()
def analyze_all(name_regex: Optional[str] = None) -> dict[str, Any]:
    """Run every check and return the report summary plus all findings."""
    proj = _project()
    rep = build_report(proj, name_regex=name_regex)
    return {
        "summary": rep["summary"],
        "naming": validate_naming(proj, name_regex=name_regex),
        "missing_status": detect_missing_status(proj),
        "dpt": detect_dpt_issues(proj),
    }


# --------------------------------------------------------------------------- #
# Generation tools (write only into the confined workspace)
# --------------------------------------------------------------------------- #
@mcp.tool()
def generate_ha_package(output_path: Optional[str] = None) -> dict[str, Any]:
    """Generate a Home Assistant KNX package YAML.

    If output_path is given, the YAML is written into the workspace and the path
    returned; otherwise the YAML text is returned inline.
    """
    proj = _project()
    res = generate_ha_yaml(proj)
    out: dict[str, Any] = {"counts": res["counts"], "review": res["review"]}
    if output_path:
        out["written"] = _safe_write(output_path, res["yaml"])
    else:
        out["yaml"] = res["yaml"]
    return out


@mcp.tool()
def generate_ets_group_addresses(fmt: str = "xml",
                                 output_path: Optional[str] = None) -> dict[str, Any]:
    """Generate an ETS-importable Group Address export.

    Args:
        fmt: 'xml' (ga-export/01, recommended) or 'csv' (native ETS layout).
        output_path: optional file inside the workspace.
    """
    proj = _project()
    if fmt == "csv":
        content = generate_ets_csv(proj)
    elif fmt == "xml":
        content = generate_ets_xml(proj)
    else:
        raise ValueError("fmt must be 'xml' or 'csv'")
    out: dict[str, Any] = {"format": fmt}
    if output_path:
        out["written"] = _safe_write(output_path, content)
    else:
        out["content"] = content
    return out


@mcp.tool()
def project_report(output_path: Optional[str] = None,
                   name_regex: Optional[str] = None) -> dict[str, Any]:
    """Produce the human-readable Markdown report (review before any import)."""
    proj = _project()
    rep = build_report(proj, name_regex=name_regex)
    out: dict[str, Any] = {"summary": rep["summary"]}
    if output_path:
        out["written"] = _safe_write(output_path, rep["markdown"])
    else:
        out["markdown"] = rep["markdown"]
    return out


@mcp.tool()
def generate_handover_pack(output_dir: Optional[str] = None) -> dict[str, Any]:
    """Generate a project handover pack (as-built deliverable for commissioning).

    Assembles an equipment inventory, group-address map by domain, command/status
    coverage, KNX Secure scope and QA state into ``handover.md``, plus a
    ``topology.svg`` diagram, the full ``group-addresses.csv`` and the
    ``ha-package.yaml``. When ``output_dir`` is given (a folder inside the
    workspace) all files are written there and the paths returned; otherwise the
    handover markdown + SVG are returned inline.
    """
    proj = _project()
    pack = build_handover(proj)
    out: dict[str, Any] = {"summary": pack["summary"]}
    if output_dir:
        d = output_dir.rstrip("/")
        written = {
            "handover": _safe_write(f"{d}/handover.md", pack["markdown"]),
            "topology_svg": _safe_write(f"{d}/topology.svg", pack["svg"]),
            "group_addresses_csv": _safe_write(f"{d}/group-addresses.csv",
                                               generate_ets_csv(proj)),
            "ha_package": _safe_write(f"{d}/ha-package.yaml",
                                      generate_ha_yaml(proj)["yaml"]),
        }
        out["written"] = written
    else:
        out["markdown"] = pack["markdown"]
        out["svg"] = pack["svg"]
    return out


@mcp.tool()
def decompose_device(order_number: str, channels: int = 1) -> dict[str, Any]:
    """Expand a device into its group-address decomposition recipe.

    A KNX actuator channel is not one GA — it expands into command/status/dimming/
    position/mode objects, each with its DPT. Given a device order number, type or
    alias (e.g. 'ZIO-MB24', 'dimmer', 'JRA/S', 'presence detector') and a channel
    count, returns the objects a professional wires per channel and the total GA
    count. Use when turning a spec/ТЗ device list into a group-address structure.
    """
    return _decompose_device(order_number, channels=channels)


@mcp.tool()
def list_device_recipes() -> list[dict[str, Any]]:
    """List the device decomposition recipes in the built-in device library."""
    return list_recipes()


@mcp.tool()
def parse_devices_from_project(path: str, output_path: Optional[str] = None,
                               password: Optional[str] = None) -> dict[str, Any]:
    """Extract exact device object models from a .knxproj / .knxprod application programs.

    Reads the manufacturer application programs (M-*) embedded in an ETS `.knxproj`
    (devices actually used) or a `.knxprod` product database, and returns each device's
    order number, app-program version, object counts and detected per-channel blocks —
    the EXACT vendor comm-object model, not a generic recipe. Read-only and PII-safe: it
    reads only vendor catalog data, never the client project (P-*/0.xml).

    Use this to build/grow the local device catalog that `decompose_device` consumes
    (set NICKOL_KNX_CATALOG to the catalog dir). If `output_path` is given, the full
    catalog is written into the workspace as device-library YAML; the return value is
    always a compact per-device summary + coverage manifest (the full object lists are
    not inlined). DPT `unverified` = the vendor app-program declares none (never guessed).
    """
    result = _parse_project(path, password=password)
    if "error" in result:
        return result
    out = _appprog_summary(result)
    if output_path:
        out["written"] = _safe_write(output_path, _appprog_to_yaml(result))
        out["written_note"] = ("Local catalog file. Point NICKOL_KNX_CATALOG at its "
                               "directory to make decompose_device return catalog-exact.")
    return out


@mcp.tool()
def check_device_parameters(path: str, password: Optional[str] = None,
                            min_group: int = 3) -> dict[str, Any]:
    """Find the device whose ETS **parameter** settings differ from its N identical
    siblings — the odd thermostat/sensor out (e.g. one thermostat with a different
    setpoint/hysteresis, one presence detector with a different detection time).

    Reads per-device parameter values straight from the `.knxproj` project part
    (data xknxproject does not expose), groups identical devices by application
    program, and returns `clear_outliers` (a strong majority with a small minority —
    likely a mistake) and `split_configs` (balanced 2+ variants — review, often two
    zones). Numeric config parameters are listed first; names are resolved from the
    device application program. Read-only, no ETS/bus. Give a real `.knxproj` `path`
    (a password-protected/encrypted project cannot be read)."""
    return _check_device_parameters(path, password=password, min_group=min_group)


@mcp.tool()
def check_matter() -> dict[str, Any]:
    """Matter-readiness lint: which controllable functions round-trip to a Matter
    cluster (have command + status + a decodable DPT) and which won't."""
    return matter_readiness(_project())


@mcp.tool()
def grade_completeness() -> dict[str, Any]:
    """Grade the project: bare functional skeleton vs as-built grade — by the presence
    of the professional patterns (central macros, device tuning, astro/meteo, monitoring,
    deep metering, scenes, reserves, a debug main)."""
    return completeness_grade(_project())


@mcp.tool()
def check_energy() -> dict[str, Any]:
    """Check the metering/energy domain (energy DPTs 13.x / 14.056) and suggest a
    per-circuit / PV / battery / EVSE structure for the HA energy dashboard."""
    return energy_scaffold(_project())


@mcp.tool()
def suggest_names() -> dict[str, Any]:
    """Naming hygiene suggestions (empty names, status GAs missing a status keyword)."""
    return suggest_naming(_project())


@mcp.tool()
def generate_test_protocol(output_path: Optional[str] = None) -> dict[str, Any]:
    """Draft a functional acceptance protocol (per function: command → expected status,
    pass/fail/sign-off) as Markdown. Execution is manual/on-site; this only drafts it."""
    res = test_protocol(_project())
    out: dict[str, Any] = {"functions": res["functions"]}
    if output_path:
        out["written"] = _safe_write(output_path, res["markdown"])
    else:
        out["markdown"] = res["markdown"]
    return out


@mcp.tool()
def diff_projects(path_a: str, path_b: str,
                  password_a: Optional[str] = None,
                  password_b: Optional[str] = None) -> dict[str, Any]:
    """Semantic diff between two .knxproj files (path_a = base/old, path_b = new):
    added / removed GAs, DPT changes, renames, security-flag changes. Read-only."""
    return _diff_projects(path_a, path_b, password_a=password_a, password_b=password_b)


@mcp.tool()
def generate_knx_iot(output_path: Optional[str] = None) -> dict[str, Any]:
    """Export a KNX IoT semantic view (Turtle/RDF) of the project's functional
    datapoints — a pragmatic skeleton for the IP-native model, for review."""
    proj = _project()
    turtle = generate_knx_iot_turtle(proj)
    if output_path:
        return {"written": _safe_write(output_path, turtle)}
    return {"turtle": turtle}


@mcp.tool()
def workspace_info() -> dict[str, Any]:
    """Show the confined output workspace and the safety guarantees."""
    return {
        "workspace": str(_WORKSPACE),
        "bus_access": False,
        "note": "This server never connects to a KNX/IP bus. It only reads the "
                ".knxproj and writes files inside the workspace. Use a Git MCP / "
                "filesystem MCP to version the outputs.",
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
