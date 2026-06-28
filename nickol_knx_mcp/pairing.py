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
