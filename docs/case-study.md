# Case study — from a spec PDF to a validated 662-GA KNX structure, in minutes

🇷🇺 **Русская версия:** [case-study.ru.md](case-study.ru.md)

## The question
How far can a project **specification alone** be turned into a finished, standards-correct KNX
group-address structure — and how close would it get to professional work?

## Input
A real residential project — **14 rooms (~155 m²)**, Zennio-based: switched + dimmed lighting,
electric underfloor heating, ventilation with heat recovery, motorised curtains,
water / electricity / heat metering, leak & fire safety — described **only in a 42-page technical
specification (PDF)**. No group addresses, no DPTs, no naming were given: the spec lists equipment
and functions, not a KNX structure.

## The workflow
```
spec PDF
   │  an AI assistant, grounded in the KNX Association standard + industry practice,
   ▼  DESIGNS the full group-address structure
GA structure (taxonomy · naming · DPTs · command/status pairs · scenes · reserves)
   │  nickol-knx-mcp VALIDATES it and GENERATES the outputs
   ▼
Home Assistant package  +  ETS-importable group-address XML
```

## Output
- **662 group addresses** across **10 functional domains**, as a `ga-export/01` XML ready for ETS
  *Import Group Addresses* → place devices → export `.knxproj`.
- Produced in **minutes**.

## The check — against a professional reference implementation of the same project
| Metric | Result |
|---|---|
| Structural match | **96 %** (662 vs 687 GA) |
| Domain taxonomy | **10 / 10 identical** |
| Address names | **118 byte-identical**, 68 % with a close analog |
| DPT discipline | exact sub-types throughout; DPT 5.001 ≈ 1 : 1 |
| Validation (nickol-knx-mcp) | **0 errors**; reserve / logic noise auto-classified |
| Home Assistant | **9 climate zones · 11 shutters · 12 dimmers** + sensors, generated directly |

## What it shows
The standardised, time-consuming **"skeleton"** of a KNX project — the part defined by the standard
and the equipment — can be auto-designed to **near-professional quality in minutes, vs the days** of
manual group-address work. That frees the engineer's time for the genuinely creative part: the
project-specific logic, which stays the engineer's craft (the residual few % are exactly those
one-off logic functions).

## Honesty notes
- **No client data or project files are shared.** The reference implementation is used only as an
  anonymous benchmark; the case study reports parameters and match figures, nothing identifying.
- The **design** is produced by an AI assistant grounded in KNX knowledge (the KNX Association
  standard + broad industry practice). **nickol-knx-mcp's role** is read-only validation and
  Home Assistant / ETS export — it never connects to a live bus.
- Figures are from a structure that actually passed the tool's own checks (0 errors).
