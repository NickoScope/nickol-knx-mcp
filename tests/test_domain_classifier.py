"""P5 contextual domain classification: a DPT alone must not decide the domain.
A 1-bit switch is domain-agnostic — the name (then the main-group context) decides,
and with no signal the honest answer is 'unknown', never a guessed 'lighting'.
Matching is by word boundary so short tokens like 'ac' don't fire inside 'terrace'.
"""
from nickol_knx_mcp.project import build_loaded_from_raw, _domain_from_text, _classify_category


def _ga(addr, name, dmain, dsub):
    return {"name": name, "identifier": f"GA-{addr}", "raw_address": 0, "address": addr,
            "project_uid": None, "dpt": {"main": dmain, "sub": dsub}, "data_secure": False,
            "communication_object_ids": [], "description": "", "comment": ""}


def _proj(gas, ranges=None):
    raw = {"info": {"group_address_style": "ThreeLevel", "schema_version": "21"},
           "group_addresses": gas, "communication_objects": {}, "devices": {},
           "functions": {}, "topology": {}, "group_ranges": ranges or {}}
    return build_loaded_from_raw(raw, "t.knxproj")


def main():
    # --- word-boundary safety: 'ac' must NOT fire inside 'terrace' ---
    assert _domain_from_text("Terrace light") == "lighting", "'ac' fired inside 'terrace'"
    assert _domain_from_text("Living room AC") == "hvac"
    assert _domain_from_text("Кухня кондиционер") == "hvac"
    assert _domain_from_text("Bedroom blind position") == "shutter"
    assert _domain_from_text("Relay 3") is None       # no domain word -> None
    assert _domain_from_text("Kitchen socket") is None  # sockets aren't a modelled domain

    # --- name over an agnostic 1-bit DPT: AC on/off is HVAC, not lighting ---
    for variant in ("Living room AC on/off", "A/C кухня", "air conditioner bedroom",
                    "Кондиционер гостиная"):
        assert _classify_category(variant, "", "", 1, 1, "lighting") == "hvac", variant

    # --- a bare, context-less 1-bit switch is honestly unknown (not 'lighting') ---
    assert _classify_category("Relay 3", "", "", 1, 1, "lighting") == "unknown"
    assert _classify_category("Living room fireplace on/off", "", "", 1, 1, "lighting") == "unknown"

    # --- main-group context disambiguates a soft DPT when the name is silent ---
    assert _classify_category("Relay 3", "Lighting", "Switch", 1, 1, "lighting") == "lighting"
    assert _classify_category("Kanal 5", "Освещение", "", 1, 1, "lighting") == "lighting"
    # but a NON-actuator range name (Scenes/Sensors) must NOT retype a 1-bit command
    assert _classify_category("Fireplace on/off", "Central / Scenes", "", 1, 1, "lighting") == "unknown"

    # --- 5.001 is soft (brightness OR position): name disambiguates without conflict ---
    assert _classify_category("Bedroom blind position", "", "", 5, 1, "lighting") == "shutter"
    assert _classify_category("Kitchen pendant value", "", "", 5, 1, "lighting") == "lighting"  # default

    # --- strong DPT contradicted by an explicit name -> honest unknown (a conflict) ---
    assert _classify_category("Bathroom fan", "", "", 3, 7, "lighting") == "unknown"   # dimming vs fan
    assert _classify_category("Foyer blind", "", "", 9, 4, "sensor") == "unknown"      # lux DPT vs blind
    # 9.001 temperature is SOFT: a weather-named temp re-domains to sensor without conflict
    assert _classify_category("Weather outdoor temperature", "", "", 9, 1, "hvac") == "sensor"
    # a measurement in a passive (Sensors) main takes the range's domain...
    assert _classify_category("Gostinaya temperatura", "Sensors", "", 9, 1, "hvac", "sensor") == "sensor"
    # ...but a passive range never retypes a COMMAND
    assert _classify_category("Kanal 7", "Sensors", "", 1, 1, "lighting", "command") == "unknown"
    # ...but agreement keeps the domain
    assert _classify_category("Living room dimmer", "", "", 3, 7, "lighting") == "lighting"

    # --- Cyrillic air-con abbreviations + colloquial 'сплит' (dogfood find) ---
    for variant in ("а/с кухня вкл/выкл", "А/С детская 1 on/off", "Сплит Kids 2 status"):
        assert _domain_from_text(variant) == "hvac", variant
    # plural 'spots' must match the lighting prefix
    assert _domain_from_text("Terrace spots on/off") == "lighting"

    # --- end to end through the model: an AC switch in the HVAC main is HVAC ---
    p = _proj({"3/0/1": _ga("3/0/1", "Master bedroom AC on/off", 1, 1)})
    assert p.gas["3/0/1"].category == "hvac"

    # --- middle-0 range must not overwrite the MAIN range's name (dogfood find):
    # a middle group 0 starts at the same raw address as its main, so the old
    # modulo heuristic clobbered "Освещение" with "Вкл/Выкл" and the range
    # rescue silently died. Depth decides now. ---
    ranges = {"r1": {"name": "Освещение", "address_start": 2048, "group_ranges": {
        "r10": {"name": "Вкл/Выкл", "address_start": 2048, "group_ranges": {}}}}}
    p2 = _proj({"1/0/9": _ga("1/0/9", "Kanal 9", 1, 1)}, ranges)
    assert p2.gas["1/0/9"].main_name == "Освещение", p2.gas["1/0/9"].main_name
    assert p2.gas["1/0/9"].middle_name == "Вкл/Выкл", p2.gas["1/0/9"].middle_name
    assert p2.gas["1/0/9"].category == "lighting", \
        "main-range name must rescue a context-less switch in the lighting main"

    print("test_domain_classifier: OK — DPT is one signal among name + main-group context; "
          "AC/kondicioner is HVAC, bare switches are unknown, 5.001 disambiguates by name, "
          "strong-DPT vs name is a conflict, and 'ac' never fires inside 'terrace'.")


if __name__ == "__main__":
    main()
