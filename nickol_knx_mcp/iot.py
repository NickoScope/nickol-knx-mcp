"""C1 — KNX IoT semantic export (Turtle / RDF).

KNX IoT is the IP-native future: an installation is described by a *semantic* model
(functions, datapoints, DPTs) rather than only classic group addresses. This module
emits a Turtle/RDF view of the project's functional group addresses from the same graph
we already build for the GA XML — one source of truth, two exports. Read-only file
generation; no bus.

The output is a pragmatic semantic skeleton (datapoint per functional GA with its DPT,
name, role and 3-level address). It is not the full certified KNX IoT ontology, and says
so — a starting point for an IoT-native description, reviewed before use.
"""

from __future__ import annotations

from .project import LoadedProject
from .intent import INTENT_FUNCTIONAL


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def generate_knx_iot_turtle(project: LoadedProject) -> str:
    """Emit a Turtle/RDF semantic view of the project's functional datapoints."""
    lines = [
        "@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix knx:  <https://ns.knx.org/> .",
        "@prefix dpt:  <https://ns.knx.org/dpt/> .",
        "@prefix proj: <urn:nickol-knx:project#> .",
        "",
        "# KNX IoT semantic view — generated read-only from the .knxproj.",
        "# Pragmatic skeleton (datapoint per functional group address), NOT the full",
        "# certified KNX IoT ontology. Review before use.",
        "",
        f'proj:project a knx:Installation ;',
        f'  rdfs:label "{_esc(project.info.get("name","KNX project"))}" ;',
        f'  knx:groupAddressStyle "{_esc(project.info.get("group_address_style","ThreeLevel"))}" .',
        "",
    ]
    n = 0
    for ga in project.gas.values():
        if ga.intent != INTENT_FUNCTIONAL or ga.dpt_main is None:
            continue
        n += 1
        node = "proj:ga_" + ga.address.replace("/", "_")
        lines += [
            f"{node} a knx:Datapoint ;",
            f'  knx:groupAddress "{ga.address}" ;',
            f'  rdfs:label "{_esc(ga.name)}" ;',
            f"  knx:datapointType dpt:{(ga.dpt or '').replace('.', '-') or 'unknown'} ;",
            f'  knx:role "{ga.kind}" ;',
            f'  knx:function "{_esc(ga.category)}" ;',
            f"  knx:secure {'true' if ga.data_secure else 'false'} .",
            "",
        ]
    lines.insert(len(lines), f"# {n} functional datapoints exported.")
    return "\n".join(lines)
