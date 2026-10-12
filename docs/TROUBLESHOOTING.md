# Troubleshooting

HAVRV mirrors selected Home Assistant entities; start by checking each source
entity in Home Assistant. If the source itself is missing, unavailable, or
incorrect, resolve that with the integration that provides it.

## A mapped entity is missing

Open HAVRV's **Options** and check that the intended entity is selected in the
correct system group. System mappings accept sensors, binary sensors,
switches, lights, and climate entities. HAVRV does not discover hardware or
infer mappings from entity names.

## A HAVRV entity is unavailable

Check the original entity in Home Assistant. A missing, `unknown`, or
`unavailable` source makes its HAVRV mirror unavailable until the source
returns a usable state.

## A control has no effect

Confirm that the selected source entity is available and can be controlled
directly in Home Assistant. HAVRV forwards the corresponding standard domain
service call; it does not override source permissions or capabilities.

## A tank reading, percentage, or status is missing

Check the tank's source selection in **Options** and verify that the source
reports a usable level. **Percentage** requires a capacity in the RV profile.
**Status** requires both warning and problem percentages. Tank types are
selected explicitly; HAVRV does not identify them from entity names.

## The operation mode is unknown

HAVRV does not detect or default the operation mode. Choose a mode on the
**Operations** device or with the `select.select_option` action. The last
selection is restored after a restart; it is lost if the RV profile is removed.

## A tire reading or problem state is missing

Check the per-tire pressure, temperature, and battery source selections and
confirm those sources are available. Pressure and temperature comparisons
require recognized units when a source supplies a unit. Check that configured
limits are appropriate for the vehicle and the profile's selected measurement
system.

Pressure-trend predictors can report unknown when the source is unavailable or
they do not yet have enough history. Their history is held in memory, so it
starts over after a Home Assistant restart or integration reload. Slow-loss
prediction also requires a temperature source.

## An All Tire Monitor comparison is unavailable

Spreads need at least two usable comparable readings; outlier analysis needs
at least two usable readings with three prior readings per tire in the
preceding 12 hours. Outlier history is held in memory and resets after a Home
Assistant restart or integration reload. Check source availability, numeric
values, and units. Axle pressure is compared by axle; dual-wheel temperature
is split into inner and outer comparisons. Separate all-tire groups compare
every configured tire.

## A profile value is incorrect

Use the config entry's **Reconfigure** action to update saved vehicle details.
The profile name cannot be changed there; remove and recreate the profile if
it needs a new name. Existing mappings are not changed by reconfiguration.

Profile dimensions and capacities are specifications entered by the user.
Confirm their values and selected unit system against a reliable source, such
as coach documentation or vehicle labels. Home Assistant may display
measurements in its globally selected unit system.

## The RV card or dashboard is missing or wrong

- If **HAVRV RV overview** is not offered when adding a card, or a dashboard
  shows "Custom element doesn't exist", restart Home Assistant after installing
  or updating HAVRV. Then refresh the browser, clearing its cache if needed.
  On the companion app, use **Settings → Companion app → Debugging → Reset
  frontend cache**.
- If the card reports that no RV profile was found, add a HAVRV profile, or set
  `device_id` to a HAVRV device.
- If an axle or wheel is missing, check the axle layout and wheel
  configuration in the RV profile. If a tank is missing, configure a capacity
  or source entity for it.
- A gray wheel or tank has no pressure or percentage reading. Check its source
  entity, as described in the sections above.

## You need to change or remove a source mapping

Use the integration's **Options** to change system mappings, tank selections,
tire sources, or tire limits. Removing the HAVRV config entry removes HAVRV's
devices and exposed entities, but does not remove source entities or their
integrations.

For configuration steps, see [Set up HAVRV](SETUP.md). For details about
entity behavior and thresholds, see [Features and behavior](FEATURES.md).
