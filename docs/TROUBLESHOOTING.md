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
at least three. Check source availability, numeric values, and units. Pressure
is compared by axle. Dual-wheel temperature is split into inner and outer
comparisons.

## A profile value is incorrect

Use the config entry's **Reconfigure** action to update saved vehicle details.
The profile name cannot be changed there; remove and recreate the profile if
it needs a new name. Existing mappings are not changed by reconfiguration.

Profile dimensions and capacities are specifications entered by the user.
Confirm their values and selected unit system against a reliable source, such
as coach documentation or vehicle labels. Home Assistant may display
measurements in its globally selected unit system.

## You need to change or remove a source mapping

Use the integration's **Options** to change system mappings, tank selections,
tire sources, or tire limits. Removing the HAVRV config entry removes HAVRV's
devices and exposed entities, but does not remove source entities or their
integrations.

For configuration steps, see [Set up HAVRV](SETUP.md). For details about
entity behavior and thresholds, see [Features and behavior](FEATURES.md).
