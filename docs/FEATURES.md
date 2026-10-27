# HAVRV features and behavior

Use this page as a reference for the entities HAVRV creates and how they
behave. For installation and configuration steps, see the [setup
guide](SETUP.md).

## Management page

The integration entry's gear opens a dedicated, admin-only page with Overview,
RV profile, Power, Tanks, Tires and System mappings. It edits the same config
entry as native forms and configuration-number entities. All sections share one
in-memory draft and one **Apply changes** operation, with validation, removal
review and stale-draft detection. Existing IDs and source ownership are retained.
The monitoring dashboard is a separate view. Native options/reconfigure
flows remain available as recovery paths.

Inputs place their clear action alongside the control. Source names appear
beside field titles, with live values that open Home Assistant's entity details
and history dialog without leaving or saving the draft. Multiple mappings have
an individual value/details action for each selected source. Missing entities
remain visible; history availability depends on Home Assistant's recorder.
Live values use Home Assistant's localized entity-state formatting and plain
theme-colored text, not action-button badges.
Power and Tires use icon-based selection lists instead of dropdowns, showing
each bank, supply or tire's draft mapping count and live unavailable-source count.
Selecting another item never saves or discards the profile-wide draft.
On small screens the selection rows scroll horizontally rather than becoming a
dropdown.
Overview groups links under **Configure your systems**, includes a draft RV
profile summary, and links to the profile-filtered device/entity registries.
Its unavailable-source links open the corresponding editor; these describe source
availability, not an inferred safety or power-supply status.
The Tires tab includes a clickable RV position diagram generated from the
draft axle layout, alongside its selection list. Filled wheels indicate the
selected position; dashed wheels indicate a missing or unavailable mapped source,
not a vehicle safety assessment.

## System entity mappings

HAVRV organizes selected entities beneath the RV device and child devices for
system groups. It mirrors state changes reported by Home Assistant; it does
not poll source entities.

| Source domain | HAVRV behavior |
| --- | --- |
| `sensor` | Mirrors the current state and metadata, converting compatible numeric units to the profile system. Other available states are exposed as text. |
| `number`, `input_number` | Read-only numeric sensor mirrors; no number-setting actions are forwarded. Template numbers and sensors use their actual entity domains. |
| `binary_sensor` | Mirrors on/off state, device class, and icon. |
| `switch` | Mirrors state and forwards turn-on, turn-off, and toggle actions to the selected source. |
| `light` | Mirrors state and color modes and forwards supported Home Assistant light service arguments. |
| `climate` | Mirrors the source climate state and supported attributes and forwards climate control actions. |

If a source is missing, `unknown`, or `unavailable`, its HAVRV mirror is
unavailable until a usable source state returns. Source integrations remain
responsible for communicating with and controlling the actual devices.

Generic numeric mirrors convert recognized length, volume, pressure, temperature,
mass, area and speed units to the profile's metric or US customary units,
including helpers without a device class. Other units remain passthrough.
Home Assistant's global unit preference does not replace these profile defaults;
explicit per-entity display-unit overrides still work. Original source states
are never modified.

## RV profile specifications

The main RV device's **Configuration** section exposes editable number inputs
for overall height, length, and width and fuel/fresh/gray/black-water tank
capacities. These are saved specifications, not live measurements. Unknown
specifications remain `unknown` until entered; HAVRV never guesses them.
Dimensions and capacities must be greater than zero and use the profile's
selected units (m/L or ft/US gal), not Home Assistant's global defaults.
Explicit per-entity unit overrides remain supported and are converted when
writing values back to the profile's units.

Coach year, chassis manufacturer/make, builder/model, coach identifier, storage
zone, measurement system, rear axle count, wheel configuration, and tag-axle
presence are read-only sensors in **Diagnostics**. Edit those values with
**RV profile** on the management page or **Reconfigure**; axle count and coach year are structural/reference fields,
not quantity inputs.

Configuration also exposes warning/problem percentages for all three water
tanks and, when tire positions exist, low/high pressure limits for the
applicable front/rear/tag groups, a shared high-temperature limit, and a
low-battery limit. Tank defaults are 50% warning / 25% problem for fresh
water and 50% warning / 75% problem for waste water; battery defaults to 20%.
Pressure and temperature controls show the actual saved limit. An unset limit
remains `unknown` and inactive, preserving existing optional-limit behavior.
Its `suggested_default` attribute matches the form's advisory defaults:
100/150 psi (689.5/1034.2 kPa) and 150 F (65.6 C). Setting one pressure limit
also saves its companion's suggested default if that companion was unset.
These suggestions are not manufacturer-specific safety limits.

Fresh-water problem must stay below warning; waste-water problem must stay
above warning. Pressure high must exceed low. Percent limits must be between
0 and 100; pressure and high-temperature limits must be non-negative and all
values finite. To move a pair beyond its current range, adjust the bounding
limit first. Invalid changes report an error and leave configuration unchanged.

Device edits persist in the same profile data/options as the configuration
forms and trigger a normal integration reload so readings and detection use
the new values. Unrelated settings and source mappings are retained. Reloading
resets in-memory tire analysis history, as other configuration changes do.
The controls also support the standard `number.set_value` action.

On upgrade, main-device dimension and fuel-capacity sensors are replaced by
`number` entities; update dashboards or automations that used those old
`sensor` entity IDs. Water-tank capacity sensors remain on the tank devices,
with editable capacity numbers on the main RV device. Read-only diagnostic
profile sensor IDs are unchanged. Source selections are editable on the
management page or through the native options fallback.

## Tow device

Every RV profile, including existing name-only profiles, automatically has a
**Tow** child device. No setup field, source mapping or helper is required.
Open the device in **Settings → Devices & services → HAVRV** to edit:

| Entity | Behavior |
| --- | --- |
| Towing | Runtime on/off switch; defaults to off |
| Type | Runtime dropdown: Car or Trailer; defaults to Car |
| Weight | Runtime number, initially unknown; finite non-negative values in kg for metric profiles or lb for US customary |

These are user-reported operational values, not hardware controls or measured
loads. Standard `switch.turn_on`/`turn_off`/`toggle`, `select.select_option` and
`number.set_value` actions work without saving configuration or reloading the
integration. Type and weight remain editable and retained while towing is off.
All three values restore after reloads and normal Home Assistant restarts.
Changing profile units converts the restored weight; it does not reinterpret
the old number. Explicit per-entity display-unit overrides are supported.

The dashboard draws a car outline or trailer behind the RV only while Towing
is on and Type is available. Off, unknown or unavailable towing status reserves
no space. An unknown weight shows **No data**, not a guessed load. The
`show_tow` dashboard option can hide the graphic without changing runtime state.
The device controls remain available even when the graphic is hidden.

Weight is the user-entered total towed weight, not tongue weight, a towing
rating or a safe-load calculation. No manufacturer-specific limits, towing
procedures, braking checks or compatibility claims are inferred.

## Power-source devices

Each RV has independently numbered **House Batteries** and **Chassis Batteries**
bank devices, plus a logical **Inverter**, **Generator**, and **Shore Power**.
Bank counts default to one each and can be changed in **RV profile** on the
management page or through native **Reconfigure**. Each
bank is a complete independent unit; HAVRV does not assume its internal wiring.

| Entity | Meaning |
| --- | --- |
| Voltage | A declared DC-bank or AC-output/supply reading, converted to V |
| Current | A declared current reading, converted to A; source sign is preserved |
| Shore line voltage/amps | Optional readings per AC line, converted to V/A |
| Shore line frequency/watts | Optional readings per AC line, converted to Hz/W |
| Shore energy | One shared cumulative source in kWh; resets follow the underlying meter |
| Enabled | Read-only on/off status from its explicitly mapped source |
| Charging (banks only) | Read-only status reporting whether that particular bank is charging |
| Warning | Optional read-only mapped advisory status; on gives the source box an amber dot/tint |
| Problem | Optional read-only mapped problem status; on gives a red dot/tint, taking precedence over Warning |
| Nominal voltage (banks only) | Configured specification: 12, 24 (default), or 48 V DC |
| Nominal capacity (banks only) | Optional configured total capacity in Ah; no default |
| Dashboard placement | Diagnostic metadata for optional overview placement |

Live entities are created only for explicitly selected mappings. Missing,
unavailable, nonfinite or nonnumeric electrical readings are unavailable.
Recognized compatible electrical units are converted; incompatible units are
unavailable. Unitless helpers are interpreted as V or A according to the
declared mapping. Both profile measurement systems use V/A/Ah. Explicit
per-entity display-unit overrides remain respected.

Shore Power supports one or two lines, defaulting to two for a new
configuration. Existing mappings without a line count remain single-line;
their entity identities are preserved as Line 1 when expanded. Each reading
is optional and independent. Frequency, watts, and shared energy support the
same numeric source domains and compatible-unit conversion; unitless sources
use Hz, W, and kWh respectively. Negative energy is invalid. No missing reading
is calculated, and there is no HAVRV reset control or trip-energy accumulator.
Hughes Watchdog may supply readings through its existing Home Assistant
entities; HAVRV does not communicate with that hardware directly.

House banks typically supply domestic DC loads and the inverter; chassis banks
serve engine starting and vehicle systems. An inverter converts battery DC
to AC for its supported circuits, while generator and shore supply AC.
Chargers/converters and alternator interfaces may charge batteries when power
is available, subject to installed equipment, control logic, and loads.
The [EcoFlow electrical-system overview](https://www.ecoflow.com/us/blog/rv-power-systems-setup-guide)
provides general background; actual vehicle documentation and component labels
take precedence.

**Enabled is not proof of supplying power, and source availability is not proof
of charging.** HAVRV does not infer Charging from current sign, nominal voltage,
engine operation, shore connection, or generator state. It does not assume a
transfer-switch topology, decide which source is active, calculate state of
charge, or draw inferred power-flow arrows. The logical inverter mapping
does not automatically aggregate multiple physical units or circuits.
These states are informational, not generator start/stop controls or safety
interlocks.

Placement is optional, with six interior regions and an external left/right
shore connection. Each source has its own readout box beside the selected
region, with matching equipment tags instead of crossing callout lines. Colocated sources use separate
collision-free slots rather than a shared marker or bottom tiles.
No physical location is guessed. Green/gray dots and subtle box tints indicate Enabled on/off;
explicit Warning/Problem override that color, and unavailable mapped statuses
show a dashed no-data box with a hollow dot unless a known alert is active.
Box transparency and typography match the tire labels; hover or focus the
status dot for its label, or select it for the mapped entity's details.
Each source also has a battery, generator, inverter or shore-plug graphic,
associated with its box by matching tags. Banks and AC equipment are on
the coach; the shore plug is outside. Like tire shapes, equipment graphics
are green when Enabled is on, gray when off, amber/red for Warning/Problem,
and dashed/unfilled for unknown. They do not infer wiring or supply priority.
Graphics normally have a tire-comparable 44-unit footprint. Bank, inverter and
generator boxes show Enabled through color and a status dot instead of a
Yes/No row. One common legend covers electrical, tires and tanks.
Electrical boxes use consistent compact label/value rows, with any missing-data
clock and age inline after **No data**, not on a separate line.
Shore Power additionally separates its readings into Line 1 (left) and Line 2
(right) columns, with mapped Enabled and shared Energy in a divided Combined
section below. Enabled reports its own source, not the Warning/Problem color.
HAVRV applies no electrical alert thresholds; [dashboard colors](DASHBOARD.md#electrical-box-colors)
come only from the declared binary sources.

## Water-tank entities

Fresh-, gray-, and black-water level mappings are optional and selected
explicitly. A saved capacity or selected source defines a tank device with
**Level**, **Percentage**, **Status**, and a history sensor; a capacity adds
**Capacity**. Without a usable source, readings stay unavailable. Percentage
sources work without a capacity; volume sources need a compatible capacity to
derive percentage. HAVRV does not infer a tank's type from its source entity ID
or name.

The **Status** sensor (`ok`, `warning`, or `problem`) uses the configured
warning/problem pair, or the advisory defaults (fresh: 50%/25%; gray/black:
50%/75%). Fresh-water thresholds are
direction-aware for falling levels; gray- and black-water thresholds are
direction-aware for rising levels. **Last filled** (fresh water) or **Last
emptied** (gray/black water) records a crossing of fixed 95% / 5% boundaries.
That timestamp is restored after restart, and the first reading after startup
does not create an event. Fuel-level devices are not implemented.

Clearing both capacity and source removes that tank's HAVRV sensors and empty
device on reload. Existing orphaned tanks are cleaned on setup too. Thresholds
alone do not define tanks, while temporary source outages never remove a defined
tank. Original sources and unrelated entities are preserved; a device with
unrelated entities or another config entry is retained.

## Operations device

The management panel's **Operations** source page optionally maps:

- **RV location**: a `device_tracker` with finite latitude/longitude coordinates
  in [-90, 90] and [-180, 180]. HAVRV exposes a GPS `device_tracker`, using Home
  Assistant's map/zone handling rather than copying the source's home/away text.
  Valid GPS accuracy passes through in metres; absent/invalid accuracy uses Home
  Assistant's default zero (unknown precision), not a measured accuracy.
- **Detected altitude** and **Detected speed**: `sensor`, `number`, or
  `input_number`, including templates in their actual entity domains. Sources
  must declare compatible distance/speed units. Altitude may be negative; speed
  must be non-negative. Values convert to the profile's m/ft and km/h/mph,
  independently of HA's global units; explicit HA per-entity unit overrides
  remain respected.
- **Detected direction of travel**: a numeric source in the same domains, with
  unit `°` and value **0 ≤ degrees < 360**, clockwise from north (0 north,
  90 east). Select a source that actually reports travel bearing/course, not
  a compass heading unless that is the reading you intend to expose. HAVRV
  neither calculates a course from GPS fixes nor normalizes headings, converts
  compass labels, detects motion, or changes the operation mode.

All four mappings are independent and optional, with no assumed sources or
default readings. Missing, unavailable, non-finite, invalid or incompatible
sources make only their mapped entity unavailable; updates are event-driven.
Changing a source preserves the HAVRV entity identity. Clearing a mapping
removes its HAVRV entity on reload, never its original source. Diagnostics
redact travel source configuration and do not export travel readings/history.
Like any HA tracker, valid location data is visible to HA maps, history and
authorized users; HAVRV does not independently purge Recorder history.

Each RV profile has an **Operations** device with an **Operation mode**
selector: Storage, Driving, Campsite full service, Campsite minimal, or
Maintenance. HAVRV does not detect the mode; choose it manually or from an
automation with the `select.select_option` action. The mode is unset until
first selected, and the last selection is restored after a restart or reload.
The mode is informational for now: tank and tire problem detection does not
change with it, but automations and dashboards can use it.

## Tire entities

When the rear axle count is configured, HAVRV creates tire devices for the
front and configured rear axle assemblies. Single wheels are named by side;
dual wheels have separate inner and outer devices. A tag axle is inferred
when the rear axle count is greater than one; other rear assemblies use the
main rear wheel configuration.

Each tire can map pressure, temperature, and battery sources. Tire sources
may be `sensor`, `number`, or `input_number` entities. HAVRV exposes readings,
pressure/temperature/battery problem states, data-present state, and an
overall tire problem state. The same battery selector also accepts
`binary_sensor`, `input_boolean`, and `switch` entities, including template
binary sensors. Binary sensors with device class `battery` or `problem` use
Home Assistant alarm semantics: on means a battery problem and off means OK.
Other boolean sources use on=OK and off=problem. The read-only battery mirror
preserves on/off without inventing a percentage or forwarding toggle actions.
Numeric battery sources use a default low-battery limit of
20%, configurable under **Tires** or in the native options fallback; this limit
does not apply to boolean sources.
Existing numeric mappings need no migration. Existing `battery`/`problem`-class
binary mappings now follow their declared alarm semantics; remove any previous
inversion that made those alarm-class sources report on for healthy.
The dashboard accepts both on and off battery mirrors as present data.
The overall state turns on for
missing readings or when a configured limit is exceeded or cannot be evaluated.
Unavailable or invalid boolean states stay unknown, not OK, and do not count
as data present.
Pressure and temperature limits are optional and use the RV profile's units;
recognized source units are converted before comparison.

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
on each axle, plus pressure and temperature outlier-identity sensors. It also
provides a separate **All tires** group with pressure and temperature spreads
and outlier identities across every configured tire, regardless of axle or
wheel position.

Pressure readings are compared across positions on the same axle. Dual-wheel
temperatures are compared separately for inner and outer tires. A spread is
maximum minus minimum; source values with convertible units are normalized to
the profile's units, and unitless values are interpreted in those units.
Unavailable, nonnumeric, or unrecognized-unit readings are omitted. Fewer than
two usable peers makes a spread unavailable. Outlier analysis requires at
least two currently usable tires with three prior readings each.

Outliers use the standard modified z-score rule (absolute score greater than
3.5, based on each tire's own median absolute deviation over the preceding
12 hours). This history lets small groups identify a tire that departs from
its own baseline without assuming that the tires normally have identical
readings. At least three prior readings are required for at least two currently
usable tires in the group. If a tire's baseline has no variation, any
current value different from its baseline median is considered a deviation.
When no unique tire is identified, the sensor reports **No outlier**.

This is relative analysis, not an alert: there is no fixed comparison
threshold, no alert binary sensor, and no effect on individual tire problem
or pressure-trend entities. The rolling history is held in memory and resets
after a Home Assistant restart or integration reload; outlier sensors remain
unavailable until enough new readings arrive. Pressure spreads and temperature
spreads are displayed in the RV profile's selected unit, independent of Home
Assistant's unit preference. Differences can reflect sun, shade, or tire
heating; investigate readings in context and follow the tire manufacturer's
guidance.

## RV dashboard

HAVRV serves an RV overview card (`custom:havrv-rv-card`) and dashboard and
view strategies (`custom:havrv`) from the integration. The card draws the RV
from above, using the configured axle count, single or dual wheels, tag axle,
and water tanks. It shows tire pressure and temperature and tank fill levels,
colored by the HAVRV problem, trend, and tank status entities. The
card keeps pressure and temperature on one line for each single or dual tire,
including independent missing-data indicators. Crowded electrical placements
use extra nonoverlapping interior slots and outward readout lanes; see the
[R-Rear stress examples](DASHBOARD.md#placement-stress-example). The generated
dashboard adds sections for coach details, tanks, tire analysis, and each
system and power-source device. Optional electrical graphics and readout boxes
use selected regions and mapped statuses. See the [dashboard guide](DASHBOARD.md).

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
level monitoring, or safety calculations. Operation modes do not yet adjust
tank, tire, or climate limits, and pre-departure checklists or check buttons are not
implemented. Tire predictors and comparisons
are advisory and should not be treated as safety guarantees.
