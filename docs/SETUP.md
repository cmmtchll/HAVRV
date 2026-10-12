# Set up HAVRV

This guide walks through installation, adding an RV, choosing source entities,
and configuring optional tank and tire monitoring. HAVRV organizes entities
that Home Assistant already provides; it does not discover, pair with, or
control RV hardware directly.

## Before you start

- Make sure Home Assistant is running and the integrations that provide your
  RV-related entities have been set up.
- Identify the sensors, binary sensors, switches, lights, and climate entities
  you want to group. For tanks and tires, note the exact source entity and its
  unit, if it has one.
- Have reliable coach specifications available for any profile fields you
  intend to fill in. Dimensions and capacities are saved as provided; HAVRV
  does not verify them.

## 1. Install HAVRV

### HACS

1. In HACS, open **Integrations** and choose the three-dot menu.
2. Select **Custom repositories**.
3. Add `https://github.com/cmmtchll/HAVRV` with the category **Integration**.
4. Find **HAVRV** in HACS and install it.
5. Restart Home Assistant.

### Manual installation

1. Copy `custom_components/havrv` from this repository into the
   `custom_components` directory in your Home Assistant configuration
   directory.
2. Restart Home Assistant.

## 2. Add an RV profile

1. In Home Assistant, go to **Settings → Devices & services → Add integration**
   and select **HAVRV**.
2. Enter a unique profile name. Add the optional coach details and
   specifications that you know; you can leave unknown values blank.
3. Select the measurement system that matches the values you enter:
   dimensions use meters or feet, and tank capacities use liters or US gallons.
4. Select a Home Assistant zone if you want to record the RV's usual storage
   location.
5. If known, enter the number of rear axle assemblies and wheel arrangements.
   The axle count includes a tag axle: one means one main rear axle; two means
   one main axle plus a tag axle; three means two main axles plus a tag axle.

The profile can store coach year, chassis manufacturer and make, builder or
converter and model, coach identifier, overall dimensions, fuel and
fresh/gray/black-water capacities, rear axle count, and rear wheel
arrangements. These are reference specifications, not live vehicle readings.
Editable dimensions and capacities use the profile's selected measurement
system, independent of Home Assistant's global unit defaults.

Older saved profiles that predate the current axle model are not migrated.
Remove and add those profiles again to use the current setup.

## 3. Map existing system entities

During setup, optionally assign entities to system groups such as power, water,
chassis, climate, and location. Select the entity that actually represents
each function in your installation; names and entity IDs are not standardized
across RVs.

System mappings accept:

- `sensor` and `binary_sensor` entities for read-only values and states.
- `switch`, `light`, and `climate` entities for mirrored state and supported
  controls.

HAVRV creates an RV device and child devices for groups with mapped entities.
It does not rename, remove, or take ownership of the original source entities.
You can leave mappings empty and add them later in the integration's options.

## 4. Optionally configure water tanks

In the integration's **Options**, select an existing sensor for each
fresh-water, gray-water, or black-water tank level you want to expose. Tank
types are selected explicitly; HAVRV does not infer them from entity names.
Each selection creates a tank device with a live **Level** sensor. If a
capacity is saved in the RV profile, the tank device also shows **Capacity**
and a calculated **Percentage**.

You may set warning and problem percentages for a tank, but both thresholds
must be set together. Fresh water warns as the level falls; gray and black
water warn as the level rises. A configured tank gets a **Status** sensor with
`ok`, `warning`, or `problem`. Fuel-level monitoring is not implemented, even
though a fuel capacity can be stored on the profile.

## 5. Optionally configure tire monitoring

Tire positions are generated when the profile has a rear axle count. HAVRV
creates front and rear tire devices according to the configured axle and
wheel layouts. A tag axle is included when the count is greater than one.

In **Options**, choose an existing pressure, temperature, and/or battery
sensor for each tire position. Sources may be `sensor`, `number`, or
`input_number` entities. These are read-only mirrors; HAVRV does not discover
or control TPMS hardware.

You can set optional low/high pressure limits for front, rear, and tag tires,
plus a shared high-temperature limit and low-battery limit. Configure limits
only when they are appropriate for your vehicle. Pressure and temperature
limits use the profile's measurement system (kPa and °C for metric; psi and °F
for US customary); recognized source units are converted before comparison.

When tire positions are configured, HAVRV also creates an **All Tire Monitor**
device for axle comparisons. See the [feature guide](FEATURES.md) for details
on its readings and the built-in pressure-trend predictors.

## 6. Check your setup

Open **Settings → Devices & services → HAVRV** and inspect the RV device and
its child devices. Confirm that:

- The main RV device's **Configuration** section shows editable dimensions,
  capacities, and tank/tire limits; **Diagnostics** shows the other saved
  profile details read-only.
- Mapped entities follow their source states.
- Tank and tire readings appear for the source entities you selected.
- Source units and any configured limits are appropriate for your equipment.
- The **Operations** device shows an **Operation mode** selector. It is unset
  until you choose a mode; the mode does not change problem detection.

For a missing or unavailable reading, check the original source entity in Home
Assistant first. The [troubleshooting guide](TROUBLESHOOTING.md) covers common
setup issues.

## 7. Optionally add the RV dashboard

HAVRV includes an RV overview card and a dashboard that draws your configured
axles, wheels, and tanks. After installing or updating HAVRV, restart Home
Assistant and refresh your browser. Then follow the
[dashboard guide](DASHBOARD.md) to add the dashboard or the card.

## Change or remove a profile

- On the main RV device, use **Configuration** to edit dimensions, capacities,
  and monitoring limits directly. Saved changes also update **Reconfigure**
  or **Options** and reload the integration. Unknown specifications are not
  guessed. Unset optional pressure/temperature limits remain inactive until
  saved; setting one pressure limit initializes an unset companion with its
  suggested default. See the [feature guide](FEATURES.md#rv-profile-specifications)
  for defaults, units, validation, and upgrade entity-ID changes.
- Use the config entry's **Reconfigure** action to update saved coach details.
  The profile name stays the same, and system and tire mappings are not changed.
- Use **Options** to change system mappings, tank selections and thresholds,
  tire sources, and tire limits. Changes to mappings, tire sources, or tire
  limits reload the entry.
- Remove the HAVRV config entry to remove its devices and exposed entities.
  Source entities and their integrations are not removed.

See the [feature guide](FEATURES.md) for the complete behavior reference and
[troubleshooting](TROUBLESHOOTING.md) for help resolving problems.
