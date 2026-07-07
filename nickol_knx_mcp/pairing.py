"""Name-token based command/status pairing.

In real KNX projects the status/feedback GA almost never sits in the same middle
group as its command (commands in .../0/..., feedback in .../4/...). So pairing
must be driven by *name similarity within the same main group*, not by address
proximity. This module centralizes that logic so analysis and HA generation agree.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .project import GARecord, STATUS_KEYWORDS, COMMAND_KEYWORDS

_STOP = set(STATUS_KEYWORDS) | set(COMMAND_KEYWORDS) | {
    "the", "of", "and", "und", "der", "die", "das", "и", "в", "на",
    "rm", "fb",
}

# command DPT main -> acceptable status DPT mains
STATUS_COMPAT = {
    1: {1, 5},     # switch/up-down -> 1.x state or 5.x position feedback
    3: {1, 5},     # relative dim -> on/off or brightness feedback
    5: {5},        # scaling setpoint -> scaling feedback
    9: {9},        # float setpoint -> float feedback
}


def base_tokens(name: str) -> set[str]:
    low = name.lower()
    for ch in "/-_.,()[]:":
        low = low.replace(ch, " ")
    return {t for t in low.split() if t and t not in _STOP and len(t) > 1}


def find_status(command: GARecord, candidates: Iterable[GARecord]) -> Optional[GARecord]:
    """Return the best status GA matching `command`, or None.

    A candidate matches when (a) token overlap with the command base name is at
    least min(2, len(command tokens)), and (b) category matches OR DPT main is
    compatible. Same-main-group candidates are preferred.
    """
    cmd_tokens = base_tokens(command.name)
    if not cmd_tokens:
        return None
    need = min(2, len(cmd_tokens))
    compat = STATUS_COMPAT.get(command.dpt_main or -1, {command.dpt_main})

    best: Optional[GARecord] = None
    best_score = -1
    for c in candidates:
        if c.address == command.address:
            continue
        inter = cmd_tokens & base_tokens(c.name)
        if len(inter) < need:
            continue
        if c.category != command.category and (c.dpt_main not in compat):
            continue
        score = len(inter) + (2 if c.main == command.main else 0)
        if score > best_score:
            best, best_score = c, score
    return best


# --------------------------------------------------------------------------- #
# Positional pairing school (parallel status middles, identical names)
# --------------------------------------------------------------------------- #
def _norm_name(s: str) -> str:
    return " ".join((s or "").lower().split())


def positional_status(command: GARecord, project) -> Optional[GARecord]:
    """Find a status GA by POSITION instead of by name marker.

    A widespread naming school (common around HDL-style projects) keeps statuses
    in a *parallel middle group*: command in ``main/m/s``, feedback in
    ``main/m'/s`` — same main, same sub, different middle — and duplicates the
    GA name 1:1 with no status suffix at all. A lexical marker search can never
    pair these, so `detect_missing_status` would cry wolf on every command.

    Deliberately conservative to avoid false pairs: requires exact sub match and
    an identical normalised name (or identical-plus-status-keyword), and a
    DPT-compatible candidate per STATUS_COMPAT.
    """
    want = _norm_name(command.name)
    if not want or command.main is None or command.sub is None:
        return None
    compat = STATUS_COMPAT.get(command.dpt_main or -1, {command.dpt_main})
    for c in project.gas.values():
        if c.address == command.address:
            continue
        if c.main != command.main or c.sub != command.sub:
            continue
        if c.middle == command.middle:
            continue
        n = _norm_name(c.name)
        if n != want:
            # allow the "same name + status word" variant of the same school
            if not (n.startswith(want)
                    and any(k in n[len(want):] for k in STATUS_KEYWORDS)):
                continue
        if c.dpt_main is not None and c.dpt_main not in compat:
            continue
        return c
    return None


def self_reporting(ga: GARecord, project) -> bool:
    """True when the actuator reports state on the command GA itself.

    Some integrators link the actuator's *status* communication object to the
    same group address as the command (the CO carries Read+Transmit flags), so
    the GA is its own feedback. There is then no separate status GA to find —
    and none is missing.
    """
    cos = (project.raw or {}).get("communication_objects", {}) or {}
    for cid in (ga.co_ids or []):
        co = cos.get(cid) or {}
        fl = co.get("flags") or {}
        if fl.get("read") and fl.get("transmit"):
            return True
    return False


# --------------------------------------------------------------------------- #
# Authoritative pairing from ETS Functions (roles)
# --------------------------------------------------------------------------- #
_FN_STATUS_TOKENS = ("info", "status", "state", "feedback", "rueck", "rück")
_FN_STATUS_PREFIXES = ("Info", "Status", "State", "Feedback")


def _role_is_status(role: str) -> bool:
    r = (role or "").lower()
    return any(t in r for t in _FN_STATUS_TOKENS)


def _status_suffix(role: str) -> str:
    """'InfoOnOff' -> 'onoff', 'StatusValue' -> 'value' (strip status prefix)."""
    r = role or ""
    for p in _FN_STATUS_PREFIXES:
        if r.startswith(p):
            r = r[len(p):]
            break
    return r.lower()


def function_status_pairs(project) -> dict[str, str]:
    """Map command-GA address -> status-GA address using ETS Function roles.

    This is the authoritative signal: ETS Functions group the GAs of one logical
    function and tag each with a role (e.g. ``SwitchOnOff`` for the command and
    ``InfoOnOff`` for the feedback). Within each function we pair every command
    role to a status role, preferring a matching role suffix
    (``InfoOnOff`` <-> ``SwitchOnOff``) and otherwise falling back to the single
    status GA in that function. Names are never needed, so a feedback GA called
    just "Status" still pairs correctly.
    """
    pairs: dict[str, str] = {}
    for fn in (project.functions or {}).values():
        roles = fn.get("group_addresses", {}) or {}
        cmds: list[tuple[str, str]] = []
        stats: list[tuple[str, str]] = []
        for key, ref in roles.items():
            addr = ref.get("address", key)
            role = ref.get("role") or ""
            (stats if _role_is_status(role) else cmds).append((addr, role))
        valid_stats = [(a, r) for a, r in stats if a in project.gas]
        if not cmds or not valid_stats:
            continue
        for caddr, crole in cmds:
            if caddr not in project.gas:
                continue
            partner = None
            for saddr, srole in valid_stats:
                suf = _status_suffix(srole)
                if suf and suf in crole.lower():
                    partner = saddr
                    break
            if partner is None:
                partner = valid_stats[0][0]
            pairs[caddr] = partner
    return pairs
