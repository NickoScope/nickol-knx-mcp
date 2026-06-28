# Demo House — the "brain" (Home Assistant smart layer)

Sophisticated control logic for the synthetic [`demo-home.knxproj`](../demo-home.knxproj),
built the way the project's architecture demands:

> **KNX (ETS)** is the body — group addresses are the muscles (commands) and nerves
> (status/sensors). It runs autonomously. **Home Assistant** is the *brain* — all the
> time/season/presence-aware logic and statistics live here, reading **real** KNX state.

This is a **design demo** (no live bus). It is valid, deployable Home Assistant YAML built on
[official best practices](https://www.home-assistant.io/docs/) — native helpers
(`utility_meter`, `history_stats`, `statistics`, `derivative`, `trend`, `threshold`, `schedule`,
`integration`, `min_max`, `group`) wherever possible, trigger-based template sensors only for
genuinely multi-factor derived context, correct automation modes, `entity_id` (never
`device_id`), and `color_temp_kelvin` (mireds removed in 2026.3).

---

## Architecture — 5 layers

```
┌────────────────────────────────────────────────────────────────────┐
│ L4  STATISTICS   energy meters · runtime · degree-hours · KPIs       │ 50_statistics
├────────────────────────────────────────────────────────────────────┤
│ L3  LIGHTING     circadian brightness/CCT · motion+presence · scenes │ 40_lighting_engine
│ L2  CLIMATE      multi-factor setpoint · changeover · adaptive preheat│ 30_climate_engine
├────────────────────────────────────────────────────────────────────┤
│ L1  HOME MODE    Home/Away/Night/Eco/Guest/Vacation state machine     │ 20_home_mode
├────────────────────────────────────────────────────────────────────┤
│ L0  SENSES       season · daypart · weekend · occupancy · comfort     │ 10_context_sensors
│ L0  HELPERS      input_*/schedule/timer/utility_meter                 │ 00_helpers
├────────────────────────────────────────────────────────────────────┤
│      KNX I/O      demo-home.knxproj — 239 group addresses             │  (ETS layer)
└────────────────────────────────────────────────────────────────────┘
```

Everything flows through **one source of truth**: `input_select.home_mode`. The senses feed the
state machine; the state machine + senses feed the climate/lighting engines; everything is
metered by the statistics layer.

---

## "Depends on everything" — the input matrix

| Input (sense) | Climate setpoint | Lighting | Mode machine | Statistics |
|---|:---:|:---:|:---:|:---:|
| **Time of day / daypart** (sun elevation) | ✅ profile | ✅ circadian b/CCT | ✅ night | ✅ tariff |
| **Day of week** (weekday/weekend schedule) | ✅ wake later | — | ✅ wake window | ✅ weekly |
| **Season** (month) + **outdoor temp** | ✅ trim + changeover | ✅ floor at night | ✅ heat/cool | ✅ degree-hours |
| **Presence/occupancy** (per zone, motion+hold) | ✅ setback | ✅ motion lights | ✅ Away/Home | ✅ dwell time |
| **Home mode** (Away/Night/Vacation/Eco) | ✅ deep setback / frost | ✅ all-off / sim | (is the state) | ✅ occupied-h |
| **Window contacts** | ✅ suspend heating | — | — | — |
| **CO₂ / air quality** (trend + threshold) | — | — | ✅ → Eco | ✅ exceedance |
| **Lux / darkness** (threshold) | — | ✅ only when dark | — | — |
| **Temperature slope** (derivative) | ✅ adaptive preheat | — | — | ✅ |

The climate **target setpoint** (`sensor.living_target_setpoint`) is the centrepiece: a single
trigger-based template that folds **8 inputs** into one number — daypart profile → weekend hold →
occupancy setback → home-mode override → seasonal trim / cooling target → window interlock →
clamp. See [`30_climate_engine.yaml`](packages/30_climate_engine.yaml).

---

## Showcase scenarios (for the demo)

1. **Winter weekday morning.** `season=winter`, `hvac=Heating`. At ~06:40 the **adaptive pre-heat**
   (`sensor.living_preheat_minutes = ΔT / rate × cold-penalty`) starts warming the Living room so
   it hits comfort exactly when the work-week schedule opens at 07:00. Lights stay off (sun below
   horizon handled by circadian + lux gate).
2. **Summer weekend afternoon.** Changeover flips to **Cooling** (outdoor > 22 °C); setpoint
   becomes a cool target; weekend holds comfort later; blinds/scenes available.
3. **Everyone leaves.** No presence 20 min → **Away**: heating drops by the away-setback, every
   light/switch turns off, the house meter keeps logging on the off-peak tariff.
4. **Bedtime.** Quiet-hours schedule → **Night**: `script.goodnight` ramps everything down, stair
   LED to 8 % @ 2200 K, bedrooms cool for sleep.
5. **Poor air.** CO₂ trend rising + threshold high for 15 min → **Eco** + a ventilation nudge.
6. **Vacation.** Frost-guard setpoints + **presence simulation** randomly toggles rooms in the
   evening so the house looks lived-in.

---

## Files

| File | Layer | Contents |
|---|---|---|
| `packages/00_helpers.yaml` | L0 | input_select/number/boolean, schedules, timers, utility_meter |
| `packages/10_context_sensors.yaml` | L0 | season, daypart, weekend, per-zone occupancy, comfort, statistics/derivative/trend/threshold |
| `packages/20_home_mode.yaml` | L1 | the state machine + seasonal heat/cool changeover |
| `packages/30_climate_engine.yaml` | L2 | KNX climate entities + multi-factor setpoint + pre-heat + interlocks |
| `packages/40_lighting_engine.yaml` | L3 | circadian sensors + adaptive motion/presence + scenes + vacation sim |
| `packages/50_statistics.yaml` | L4 | history_stats, integration→utility_meter degree-hours, KPIs, tariffs |

## Deploy (in a live HA)

```yaml
# configuration.yaml
homeassistant:
  packages: !include_dir_named demo-home-ha/packages
```

Then create the matching KNX entities from the demo project with **nickol-knx-mcp**
(`generate_ha_package`) and reconcile entity names. Two climate zones (Living, Master bedroom) are
shown in full; the same per-zone pattern repeats for all 13 zones.

> **Notes & honest caveats.** Entity IDs assume the slugified names produced by
> `generate_ha_package`. The two-climate-zone set is illustrative — production would template the
> remaining zones. In a live system, the `input_*`/`schedule`/`utility_meter` helpers are normally
> created via the UI/config-flow; here they are YAML so the whole brain is reviewable in one place.
