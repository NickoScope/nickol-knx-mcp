"""DPT classification and Home Assistant KNX platform mapping.

Central knowledge base translating a KNX Datapoint Type into:
  * a functional *category* (lighting / shutter / hvac / sensor / scene / energy / diagnostics)
  * a *kind* (command vs status vs sensor)
  * a suggested Home Assistant KNX platform + value_type

Everything here is heuristic but conservative: when in doubt we mark the
datapoint for manual review rather than guessing an entity wrong.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class DptInfo(TypedDict):
    category: str          # lighting|shutter|hvac|sensor|scene|energy|diagnostics|unknown
    kind: str              # command|status|sensor|unknown
    ha_platform: str       # switch|light|cover|sensor|binary_sensor|climate|number|scene|button|unknown
    value_type: Optional[str]  # HA value_type for sensor/number, None otherwise
    label: str             # human-readable description


CATEGORY_LIGHTING = "lighting"
CATEGORY_SHUTTER = "shutter"
CATEGORY_HVAC = "hvac"
CATEGORY_SENSOR = "sensor"
CATEGORY_SCENE = "scene"
CATEGORY_ENERGY = "energy"
CATEGORY_DIAG = "diagnostics"
CATEGORY_UNKNOWN = "unknown"

KIND_COMMAND = "command"
KIND_STATUS = "status"
KIND_SENSOR = "sensor"
KIND_UNKNOWN = "unknown"


def dpt_key(main: Optional[int], sub: Optional[int]) -> str:
    """Return a normalized 'main.sub' / 'main' string, '' if no DPT."""
    if main is None:
        return ""
    if sub is None:
        return str(main)
    return f"{main}.{sub:03d}"


def dpt_ets_token(main: Optional[int], sub: Optional[int]) -> str:
    """ETS GA-export 'DPTs' attribute token, e.g. DPST-1-1 or DPT-1."""
    if main is None:
        return ""
    if sub is None:
        return f"DPT-{main}"
    return f"DPST-{main}-{sub}"


# Exact (main, sub) overrides. None sub = applies to whole main group as fallback.
_EXACT: dict[tuple[int, Optional[int]], DptInfo] = {
    (1, 1): {"category": CATEGORY_LIGHTING, "kind": KIND_COMMAND, "ha_platform": "switch", "value_type": None, "label": "Switch on/off"},
    (1, 2): {"category": CATEGORY_UNKNOWN, "kind": KIND_COMMAND, "ha_platform": "switch", "value_type": None, "label": "Boolean"},
    (1, 3): {"category": CATEGORY_UNKNOWN, "kind": KIND_COMMAND, "ha_platform": "switch", "value_type": None, "label": "Enable"},
    (1, 5): {"category": CATEGORY_DIAG, "kind": KIND_SENSOR, "ha_platform": "binary_sensor", "value_type": None, "label": "Alarm"},
    (1, 8): {"category": CATEGORY_SHUTTER, "kind": KIND_COMMAND, "ha_platform": "cover", "value_type": None, "label": "Up/Down"},
    (1, 9): {"category": CATEGORY_UNKNOWN, "kind": KIND_SENSOR, "ha_platform": "binary_sensor", "value_type": None, "label": "Open/Close"},
    (1, 10): {"category": CATEGORY_SHUTTER, "kind": KIND_COMMAND, "ha_platform": "cover", "value_type": None, "label": "Start/Stop"},
    (1, 11): {"category": CATEGORY_LIGHTING, "kind": KIND_STATUS, "ha_platform": "binary_sensor", "value_type": None, "label": "State (status)"},
    (1, 18): {"category": CATEGORY_DIAG, "kind": KIND_SENSOR, "ha_platform": "binary_sensor", "value_type": None, "label": "Occupancy"},
    (1, 19): {"category": CATEGORY_DIAG, "kind": KIND_SENSOR, "ha_platform": "binary_sensor", "value_type": None, "label": "Window/Door"},
    (3, 7): {"category": CATEGORY_LIGHTING, "kind": KIND_COMMAND, "ha_platform": "light", "value_type": None, "label": "Dimming control (relative)"},
    (3, 8): {"category": CATEGORY_SHUTTER, "kind": KIND_COMMAND, "ha_platform": "cover", "value_type": None, "label": "Blinds control (relative)"},
    (5, 1): {"category": CATEGORY_LIGHTING, "kind": KIND_COMMAND, "ha_platform": "light", "value_type": "percent", "label": "Scaling 0-100% (brightness/position)"},
    (5, 3): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "angle", "label": "Angle 0-360°"},
    (5, 10): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "pulse", "label": "Counter pulses"},
    (10, 1): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "datetime", "value_type": "time", "label": "Time of day"},
    (11, 1): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "datetime", "value_type": "date", "label": "Date"},
    (16, 0): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "text", "value_type": "string", "label": "Character string (ASCII)"},
    (16, 1): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "text", "value_type": "string", "label": "Character string (ISO-8859-1)"},
    (19, 1): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "datetime", "value_type": "datetime", "label": "Date and time"},
    (7, 12): {"category": CATEGORY_ENERGY, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "electric_current", "label": "Current (mA)"},
    (7, 13): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "illuminance", "label": "Brightness (lux)"},
    (9, 1): {"category": CATEGORY_HVAC, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "temperature", "label": "Temperature (°C)"},
    (9, 4): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "illuminance", "label": "Illuminance (lux)"},
    (9, 5): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "wind_speed_ms", "label": "Wind speed (m/s)"},
    (9, 7): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "humidity", "label": "Humidity (%)"},
    (9, 8): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "ppm", "label": "Air quality (ppm)"},
    (9, 20): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "voltage", "label": "Voltage (mV)"},
    (9, 21): {"category": CATEGORY_ENERGY, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "current", "label": "Current (mA)"},
    (12, 1): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "pulse_4_byte", "label": "Counter (4-byte unsigned)"},
    (13, 10): {"category": CATEGORY_ENERGY, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "active_energy", "label": "Active energy (Wh)"},
    (13, 13): {"category": CATEGORY_ENERGY, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "active_energy_kwh", "label": "Active energy (kWh)"},
    (14, 19): {"category": CATEGORY_ENERGY, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "electric_current", "label": "Electric current (A)"},
    (14, 27): {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "temperature", "label": "Temperature (K → °C)"},
    (14, 56): {"category": CATEGORY_ENERGY, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "power", "label": "Power (W)"},
    (17, 1): {"category": CATEGORY_SCENE, "kind": KIND_COMMAND, "ha_platform": "scene", "value_type": None, "label": "Scene number"},
    (18, 1): {"category": CATEGORY_SCENE, "kind": KIND_COMMAND, "ha_platform": "scene", "value_type": None, "label": "Scene control"},
    (20, 102): {"category": CATEGORY_HVAC, "kind": KIND_COMMAND, "ha_platform": "climate", "value_type": None, "label": "HVAC mode"},
}

# Whole-main-group fallbacks when an exact (main, sub) is not known.
_MAIN_FALLBACK: dict[int, DptInfo] = {
    1: {"category": CATEGORY_UNKNOWN, "kind": KIND_COMMAND, "ha_platform": "switch", "value_type": None, "label": "1-bit boolean"},
    3: {"category": CATEGORY_LIGHTING, "kind": KIND_COMMAND, "ha_platform": "light", "value_type": None, "label": "4-bit relative control"},
    5: {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "1byte_unsigned", "label": "1-byte unsigned"},
    6: {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "1byte_signed", "label": "1-byte signed"},
    7: {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "2byte_unsigned", "label": "2-byte unsigned"},
    8: {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "2byte_signed", "label": "2-byte signed"},
    9: {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "2byte_float", "label": "2-byte float"},
    12: {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "4byte_unsigned", "label": "4-byte unsigned"},
    13: {"category": CATEGORY_ENERGY, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "4byte_signed", "label": "4-byte signed"},
    14: {"category": CATEGORY_SENSOR, "kind": KIND_SENSOR, "ha_platform": "sensor", "value_type": "4byte_float", "label": "4-byte float"},
    17: {"category": CATEGORY_SCENE, "kind": KIND_COMMAND, "ha_platform": "scene", "value_type": None, "label": "Scene number"},
    18: {"category": CATEGORY_SCENE, "kind": KIND_COMMAND, "ha_platform": "scene", "value_type": None, "label": "Scene control"},
    20: {"category": CATEGORY_HVAC, "kind": KIND_COMMAND, "ha_platform": "climate", "value_type": None, "label": "1-byte HVAC enum"},
}


def classify_dpt(main: Optional[int], sub: Optional[int]) -> DptInfo:
    """Classify a DPT into category / kind / HA platform."""
    if main is None:
        return {"category": CATEGORY_UNKNOWN, "kind": KIND_UNKNOWN,
                "ha_platform": "unknown", "value_type": None, "label": "No DPT assigned"}
    if (main, sub) in _EXACT:
        return dict(_EXACT[(main, sub)])  # copy
    if main in _MAIN_FALLBACK:
        return dict(_MAIN_FALLBACK[main])
    return {"category": CATEGORY_UNKNOWN, "kind": KIND_UNKNOWN,
            "ha_platform": "unknown", "value_type": None, "label": f"DPT {main}"}
