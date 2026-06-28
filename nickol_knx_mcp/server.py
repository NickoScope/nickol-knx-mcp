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
from .analyze import validate_naming, detect_missing_status, detect_dpt_issues
from .generate_ha import generate_ha_yaml
from .generate_ets import generate_ets_csv, generate_ets_xml
from .report import build_report

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
            "category": ga.category, "kind": ga.kind,
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
