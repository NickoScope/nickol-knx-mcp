"""Device library — per-device group-address decomposition recipes.

A KNX device is not "one GA". Each channel/output of an actuator expands into a set
of communication objects (command, status, dimming, position, mode, …), each with its
own DPT. This module maps a device's ``order_number`` (or a device *type*) to its
**design-time decomposition recipe** — the objects a professional integrator typically
wires per channel — so a spec/ТЗ that says "4-channel dimmer" can be expanded into the
right group-address set.

Provenance: recipes are compiled from KNX manufacturer ETS product databases and public
product documentation (Zennio, ABB), cross-checked against manufacturer "communication
objects" tables. Counts are the *typical wired* set, not the full selectable master menu
(integrators enable a subset — see the ``enablement`` note). DPTs are the canonical KNX
types per function. Where a manufacturer datum is not publicly confirmable it is omitted
rather than guessed.
"""

from __future__ import annotations

from typing import Any, Optional

# Each recipe: per-channel/per-unit object list [(function, dpt, role)].
# role: cmd | status | param.  These are the *design* objects (typical wired set).
_RECIPES: dict[str, dict[str, Any]] = {
    # ---- Zennio ------------------------------------------------------------
    "switch_output": {
        "aliases": ["ZIO-MB24", "ZIOMB24V2", "ZIO-MB8P", "ZIO-MB16P", "ZIOMB16V3",
                    "SA/S", "switch actuator"],
        "unit": "output",
        "objects": [
            ("On/Off", "1.001", "cmd"),
            ("On/Off (status)", "1.001", "status"),
        ],
        "note": "Switch output. Zennio master menu ~11 obj/output (adds scene, timer, "
                "lock, logic); ABB labels status 1.001. Typical wired: cmd + status.",
    },
    "dimmer_channel": {
        "aliases": ["ZDIDBDX4", "DIMinBOX", "ZDINDX2", "ZDINDX4", "NarrowDIM",
                    "UD/S", "dimmer"],
        "unit": "channel",
        "objects": [
            ("On/Off", "1.001", "cmd"),
            ("On/Off (status)", "1.001", "status"),
            ("Relative dimming", "3.007", "cmd"),
            ("Absolute dimming / value", "5.001", "cmd"),
            ("Brightness (status)", "5.001", "status"),
        ],
        "note": "Dimmer channel. Zennio DIMinBOX DX4 master = 23 obj/channel "
                "(adds scenes, timer, alarms, diagnostics). Typical wired = these 5.",
    },
    "led_rgbw": {
        "aliases": ["ZDI-RGBDX4", "Lumento"],
        "unit": "channel",
        "objects": [
            ("On/Off", "1.001", "cmd"),
            ("On/Off (status)", "1.001", "status"),
            ("Brightness value", "5.001", "cmd"),
            ("Brightness (status)", "5.001", "status"),
            ("Colour RGB(W)", "232.600", "cmd"),
        ],
        "note": "RGB/RGBW LED. Colour DPT 232.600 (RGB) / 251.600 (RGBW). "
                "CCT/tunable-white via a colour-temperature 5.001/7.600 object.",
    },
    "shutter_channel": {
        "aliases": ["ZIO–MBSHU8", "ZIO–MBSHU4", "MAXinBOX SHUTTER", "JRA/S", "JSB/S",
                    "shutter", "blind"],
        "unit": "channel",
        "objects": [
            ("Up/Down", "1.008", "cmd"),
            ("Stop / step", "1.010", "cmd"),
            ("Position", "5.001", "cmd"),
            ("Position (status)", "5.001", "status"),
            ("Lock", "1.003", "param"),
        ],
        "note": "Shutter/blind. ABB uses 1.008 (blind) / 1.007 (shutter) on the move "
                "object; venetian blinds add a slat-position 5.001 object.",
    },
    "floor_heating_zone": {
        "aliases": ["ZCL-8HT230", "ZCL-4HT230", "HeatingBOX", "floor heating"],
        "unit": "zone",
        "objects": [
            ("On/Off", "1.001", "cmd"),
            ("On/Off (status)", "1.001", "status"),
            ("Setpoint °C", "9.001", "cmd"),
            ("Setpoint (status)", "9.001", "status"),
            ("HVAC mode", "20.102", "cmd"),
            ("HVAC mode (status)", "20.102", "status"),
            ("Valve / contactor", "1.001", "cmd"),
            ("Valve (status)", "1.001", "status"),
        ],
        "note": "Floor-heating zone (8-object recipe). Convector/radiator = 5 "
                "(setpoint·status·mode·status·valve).",
    },
    "ac_gateway": {
        "aliases": ["ZN1CL-KLIC-DI", "KLIC-DI", "KLIC-DA", "DK-AC-KNX", "FCC/S",
                    "FCA/S", "air conditioning"],
        "unit": "unit",
        "objects": [
            ("On/Off", "1.001", "cmd"),
            ("On/Off (status)", "1.001", "status"),
            ("Mode", "20.105", "cmd"),
            ("Mode (status)", "20.105", "status"),
            ("Setpoint °C", "9.001", "cmd"),
            ("Setpoint (status)", "9.001", "status"),
            ("Fan speed", "5.001", "cmd"),
            ("Ambient temperature", "9.001", "status"),
        ],
        "note": "AC split-unit gateway. Mode 20.105 (heat/cool/fan/dry/auto) or "
                "20.102 (HVAC mode). Fan-coil (FCC/S) uses 20.102.",
    },
    "dali_group": {
        "aliases": ["ZDIDLIV2", "DALI-BOX", "DG/S", "DALI"],
        "unit": "group",
        "objects": [
            ("On/Off", "1.001", "cmd"),
            ("On/Off (status)", "1.001", "status"),
            ("Relative dimming", "3.007", "cmd"),
            ("Brightness value", "5.001", "cmd"),
            ("Brightness (status)", "5.001", "status"),
        ],
        "note": "DALI light group. Gateway addresses up to 64 ballasts / 16 groups; "
                "per-group recipe ≈ dimmer.",
    },
    "presence_detector": {
        "aliases": ["ZPDEZTPVT", "EyeZen", "presence", "motion"],
        "unit": "detector",
        "objects": [
            ("Movement / presence", "1.001", "cmd"),
            ("Movement (status)", "1.001", "status"),
            ("Luminosity (lux)", "9.004", "status"),
            ("Lock", "1.003", "param"),
            ("Scene output", "18.001", "cmd"),
        ],
        "note": "Presence/motion. Zennio master ~10 obj (adds timers, second lock, "
                "test-mode, external-on, threshold). Constant-light uses 5.010.",
    },
    "water_meter": {
        "aliases": ["ZRX-KCI4S0", "KCI", "S0 meter", "meter"],
        "unit": "input",
        "objects": [
            ("Total consumption", "13.013", "status"),
            ("This month", "13.013", "status"),
            ("Last month", "13.013", "status"),
            ("Reset", "1.001", "cmd"),
            ("Start value", "13.013", "param"),
            ("Instant / pulse", "13.013", "status"),
        ],
        "note": "Pulse/S0 meter. DPT depends on medium: energy 13.013, volume 13.x.",
    },
    "leak_sensor": {
        "aliases": ["WS", "leak", "water sensor"],
        "unit": "sensor",
        "objects": [
            ("Leak alarm", "1.005", "status"),
            ("Confirmation", "1.001", "cmd"),
        ],
        "note": "Leak sensor. Pairs with a water-shutoff valve (open/close 1.001 + status).",
    },
    "panel": {
        "aliases": ["ZVIZ50", "ZVIZ35", "Z70", "Z50", "Z35", "Flat", "ZVIF", "panel",
                    "keypad", "touch panel"],
        "unit": "panel",
        "objects": [],
        "note": "Touch panel / keypad. References EXISTING GAs (its buttons drive other "
                "devices' objects); creates ~0 new GAs of its own. Buttons are multi-DPT "
                "(1.001 / 1.008 / 3.007 / 5.010 / 18.001) bound to the target function.",
    },
}


def _lookup(key: str) -> Optional[str]:
    """Resolve an order_number / type / alias to a recipe key (case-insensitive)."""
    k = (key or "").strip().lower()
    if not k:
        return None
    if k in _RECIPES:
        return k
    for name, rec in _RECIPES.items():
        for a in rec.get("aliases", []):
            al = a.lower()
            if k == al or al in k or k in al:
                return name
    return None


def decompose_device(order_number: str, channels: int = 1) -> dict[str, Any]:
    """Return the group-address decomposition recipe for a device.

    Args:
        order_number: manufacturer order number, device type, or alias
            (e.g. 'ZIO-MB24', 'dimmer', 'JRA/S', 'presence detector').
        channels: number of channels/outputs/zones to expand (default 1).

    Returns a recipe with per-unit objects and the total GA count for ``channels``.
    """
    key = _lookup(order_number)
    if key is None:
        return {
            "matched": False,
            "query": order_number,
            "note": "No recipe found. Known types: " + ", ".join(sorted(_RECIPES)),
        }
    rec = _RECIPES[key]
    objs = [{"function": f, "dpt": d, "role": r} for (f, d, r) in rec["objects"]]
    return {
        "matched": True,
        "query": order_number,
        "type": key,
        "unit": rec["unit"],
        "objects_per_unit": len(objs),
        "objects": objs,
        "channels": channels,
        "total_ga": len(objs) * max(channels, 1),
        "note": rec["note"],
        "provenance": "compiled from KNX manufacturer ETS databases + public docs; "
                      "typical-wired set (integrators enable a subset of the master menu)",
    }


def list_recipes() -> list[dict[str, Any]]:
    """List all device decomposition recipes (type, unit, objects/unit)."""
    return [{"type": k, "unit": v["unit"], "objects_per_unit": len(v["objects"]),
             "aliases": v["aliases"]} for k, v in sorted(_RECIPES.items())]
