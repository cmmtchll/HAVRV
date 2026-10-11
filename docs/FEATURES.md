# HAVRV features and behavior

Use this page as a reference for the entities HAVRV creates and how they
behave. For installation and configuration steps, see the [setup
guide](SETUP.md).

## System entity mappings

HAVRV organizes selected entities beneath the RV device and child devices for
system groups. It mirrors state changes reported by Home Assistant; it does
not poll source entities.

| Source domain | HAVRV behavior |
| --- | --- |
| `sensor` | Mirrors the current state, unit, device class, state class, display precision, and icon. Numeric states remain numeric; other available states are exposed as text. |
| `binary_sensor` | Mirrors on/off state, device class, and icon. |
| `switch` | Mirrors state and forwards turn-on, turn-off, and toggle actions to the selected source. |
| `light` | Mirrors state and color modes and forwards supported Home Assistant light service arguments. |
| `climate` | Mirrors the source climate state and supported attributes and forwards climate control actions. |

If a source is missing, `unknown`, or `unavailable`, its HAVRV mirror is
unavailable until a usable source state returns. Source integrations remain
responsible for communicating with and controlling the actual devices.

## RV profile specifications

The RV device can expose the profile's coach details, dimensions, tank
capacities, rear axle count, wheel configuration, and tag-axle presence as
sensors. These are saved specifications, not live measurements. Dimensions and
capacities are stored in the profile's selected system and are not transformed
or verified by HAVRV. Home Assistant may display device-class measurements in
its globally selected unit system.

## Water-tank entities

Fresh-, gray-, and black-water level mappings are optional and selected
explicitly. Each selected source creates a tank device with a **Level** sensor;
a configured capacity adds **Capacity** and **Percentage** sensors. HAVRV
does not infer a tank's type from its source entity ID or name.

When both warning and problem percentages are configured, the tank also gets a
**Status** sensor (`ok`, `warning`, or `problem`). Fresh-water thresholds are
direction-aware for falling levels; gray- and black-water thresholds are
direction-aware for rising levels. **Last filled** (fresh water) or **Last
emptied** (gray/black water) records a crossing of fixed 95% / 5% boundaries.
That timestamp is restored after restart, and the first reading after startup
does not create an event. Fuel-level devices are not implemented.

## Tire entities

When the rear axle count is configured, HAVRV creates tire devices for the
front and configured rear axle assemblies. Single wheels are named by side;
dual wheels have separate inner and outer devices. A tag axle is inferred
when the rear axle count is greater than one; other rear assemblies use the
main rear wheel configuration.

Each tire can map pressure, temperature, and battery sources. Tire sources
may be `sensor`, `number`, or `input_number` entities. HAVRV exposes readings,
pressure/temperature/battery problem states, data-present state, and an
overall tire problem state. That overall state turns on for missing readings
or when a configured limit is exceeded or cannot be evaluated. Limits are
optional and use the RV profile's pressure/temperature units; recognized
source units are converted before comparison.

Tire readings are read-only mirrors. HAVRV does not discover or control TPMS
hardware. Tire problem entities do not send notifications and do not replace
manufacturer-recommended cold inflation pressures or professional inspection.

### Pressure-trend predictors

Each tire also has **Sudden pressure drop** and **Slow pressure loss**
predictors with fixed built-in thresholds:

- Sudden drop turns on when pressure falls about 8% below its recent peak
  within 5 minutes, with at least 2 minutes of history.
- Slow loss turns on when pressure falls about 3% over up to 12 hours, with
  at least 4 hours of history and 3 readings.

Pressure is compensated for temperature. Slow loss requires a temperature
source; sudden drop falls back to raw pressure when any reading in its window
lacks temperature. Pressure increases do not trigger either predictor. They
report unknown when history is insufficient or the source is unavailable.
History is in memory and restarts after Home Assistant restart or integration
reload. These heuristics do not feed the overall tire problem state and are
not a substitute for checking tires.

## All Tire Monitor

When tire positions are configured, HAVRV creates an **All Tire Monitor**
child device. It exposes pressure and temperature spreads for comparable tires
on each axle, plus pressure and temperature outlier-identity sensors.

Pressure readings are compared across positions on the same axle. Dual-wheel
temperatures are compared separately for inner and outer tires. A spread is
maximum minus minimum; source values with convertible units are normalized to
the profile's units, and unitless values are interpreted in those units.
Unavailable, nonnumeric, or unrecognized-unit readings are omitted. Fewer than
two usable peers makes a spread unavailable; fewer than three makes outlier
analysis unavailable.

Outliers use the standard modified z-score rule (absolute score greater than
3.5, based on median absolute deviation). If the median absolute deviation is
zero, a non-median value is identified only when it is the unique different
peer. Otherwise, the identity sensor reports **No outlier**.

This is relative analysis, not an alert: there is no fixed comparison
threshold, no alert binary sensor, and no effect on individual tire problem
or pressure-trend entities. Differences can reflect sun, shade, or tire
heating; investigate readings in context and follow the tire manufacturer's
guidance.

## Automations

Replace example entity IDs with the HAVRV entity IDs shown in your
installation. Home Assistant entity IDs can be customized.

Notify when a mapped water-level binary sensor turns on:

```yaml
alias: RV water level warning
triggers:
  - trigger: state
    entity_id: binary_sensor.rv_fresh_water_low
    to: "on"
actions:
  - action: notify.notify
    data:
      message: "The RV fresh-water level sensor is on."
```

Turn off a mapped water-pump switch when an entity indicates that the RV is in
storage. Configure the trigger entity and zone state to match your
installation:

```yaml
alias: Turn off RV water pump in storage
triggers:
  - trigger: state
    entity_id: binary_sensor.rv_in_storage
    to: "on"
conditions:
  - condition: state
    entity_id: switch.rv_water_pump
    state: "on"
actions:
  - action: switch.turn_off
    target:
      entity_id: switch.rv_water_pump
```

## Not implemented

HAVRV does not communicate with or discover physical RV devices. It does not
provide notifications, integration-specific triggers or conditions, fuel
level monitoring, or safety calculations. Tire predictors and comparisons
are advisory and should not be treated as safety guarantees.
