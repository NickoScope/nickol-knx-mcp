"""Classify a group address by INTENT: functional / reserve / logic / scratch.

Real ETS projects are full of intentional NON-functional group addresses:
  * **reserve**  — spare placeholders ("Резерв", "Reserve", "Spare") left for
    future use, often with no DPT on purpose;
  * **logic**    — internal/virtual signals used only inside the bus program
    (intermediate logic results, summed signals, time markers, request triggers)
    that have no physical state to read back;
  * **scratch**  — test/leftover GAs ("Новый групповой адрес", a bare "1").

Treating these like functional device GAs is what makes the tool "cry wolf" on a
real project: a spare with no DPT becomes a 🔴 error, a logic signal becomes a
"missing status" 🟡 warning. This classifier lets the checks reclassify that
noise (downgrade / skip) instead of drowning the real findings.

Name-based and deliberately conservative: when unsure we return ``functional`` so
a real problem is never hidden. Multilingual (RU / EN / DE).
"""

from __future__ import annotations

import re

INTENT_FUNCTIONAL = "functional"
INTENT_RESERVE = "reserve"
INTENT_LOGIC = "logic"
INTENT_SCRATCH = "scratch"

# Spare / reserved placeholders. "резерв" lower-cases both "Резерв" and "РЕЗЕРВ".
_RESERVE_TOKENS = (
    "резерв", "reserve", "reserved", "spare", "запас", "не использ", "unused",
    "не задейств",
)

# Internal logic / virtual signals — no physical status by design.
_LOGIC_TOKENS = (
    "промежуточн", "суммарн", "логик", "logic", "метка времени", "выход ф-ци",
    "ф-ция управлен", "ф-ции управлен", "ф-ция упр", "дубль", "вспомогат",
    "intermediate", "internal signal", "virtual", "запрос", "request",
    "годовой период", "сигнал включения", "сигнал отключения",
)

# Known scratch / default ETS names (exact, lower-cased).
_SCRATCH_EXACT = (
    "новый групповой адрес", "new group address", "new group object",
    "neue gruppenadresse",
)


def classify_intent(name: str) -> str:
    """Return one of functional / reserve / logic / scratch for a GA name."""
    raw = (name or "").strip()
    if not raw:
        # Empty name is a separate, real problem (``empty_name``); leave it
        # functional so that check still fires.
        return INTENT_FUNCTIONAL

    low = raw.lower()

    if low in _SCRATCH_EXACT:
        return INTENT_SCRATCH
    # Bare numeric placeholders like "1", "5", "12" — classic leftovers.
    if re.fullmatch(r"\d{1,3}", raw):
        return INTENT_SCRATCH

    if any(t in low for t in _RESERVE_TOKENS):
        return INTENT_RESERVE
    if any(t in low for t in _LOGIC_TOKENS):
        return INTENT_LOGIC

    return INTENT_FUNCTIONAL
