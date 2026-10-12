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

## A power reading or Charging status is missing

Select **Edit power-source mappings, specifications and placement** in
**Options** and confirm the mapping for the correct independent bank/device.
Only declared live mappings create entities. Numeric sources must have a
finite value and a compatible voltage/current unit; unitless helpers are
interpreted as V/A. Enabled and Charging must report `on` or `off`.
Charging is not inferred from a negative/positive current, an enabled inverter,
shore power, a running generator, or a running engine.

Power statuses are read-only even if their source is a switch. Use the source
integration's controls directly when needed; HAVRV does not start/stop a
generator or operate battery disconnects through these entities.

If a source section exists but its overview marker is missing, choose a
placement instead of **Not shown**, and ensure `show_power` is not `false`.
Shore Power supports only left/right outside the RV. Colocated devices share
one marker but have individual readouts beneath it. Reducing bank counts
removes the highest-numbered banks and their saved mappings; increasing
the count again does not restore removed configurations.

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

Edit dimensions and capacities in **Configuration** on the main RV device.
Other saved profile values appear read-only in **Diagnostics**; use the config
entry's **Reconfigure** action to update those vehicle details.
The profile name cannot be changed there; remove and recreate the profile if
it needs a new name. Existing mappings are not changed by reconfiguration.

Profile dimensions and capacities are specifications entered by the user.
Confirm their values and selected unit system against a reliable source, such
as coach documentation or vehicle labels. Home Assistant may display
measurements using explicit per-entity unit overrides; HAVRV's default for
these configuration inputs is the profile's selected unit system.

## A configuration limit cannot be saved

Configuration edits use the same validation as the options form. Tank
warning/problem levels must have the correct ordering for their tank type;
pressure high must exceed low. Move the bounding limit first when changing
both. Percentages must be from 0 to 100, dimensions/capacities positive, and
pressure/high-temperature limits non-negative. Invalid edits show an error and
do not change saved settings. An `unknown` pressure or temperature limit is
not active; its `suggested_default` attribute is a form suggestion, not an
active safety limit.

After upgrading, main-RV dimension and fuel-capacity entities change from
`sensor` to `number`. Update any dashboard or automation references to those
old IDs. Water-tank capacity sensors and read-only profile sensor IDs remain.

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

### The power toggle or placed electrical devices are missing

The current card editor includes **Show placed power sources** alongside
**Show header** and **Show legend**. If only the latter two appear, the browser
is running an older dashboard module, even if backend power configuration works.

Update the integration and restart Home Assistant, then reload the browser or
reset the companion app's frontend cache. In **Settings → Dashboards →
Resources** (advanced mode), remove any old manually added HAVRV JavaScript
resource such as `/local/havrv-dashboard.js` or a HACS frontend copy. HAVRV
automatically loads its bundled card; an older manual resource can register
the card first and prevent the updated implementation from taking effect.
Deleting a resource does not delete your dashboard YAML or RV configuration.

The integration's module URL includes a content revision so frontend-only
updates invalidate cached code even when the integration version is unchanged.
The repository-root JavaScript is a compatibility loader, not a second card.

With the current editor visible, confirm `show_power: true`, the selected
RV's device ID, and each device's saved **Dashboard placement**. Complete all
power-source options screens to save. Colocated devices share a numbered
marker but have separate readouts; **Not shown** omits a source from the
overview, not its generated device section.

## You need to change or remove a source mapping

Use the integration's **Options** to change system mappings, tank selections,
tire sources, or tire limits. Removing the HAVRV config entry removes HAVRV's
devices and exposed entities, but does not remove source entities or their
integrations.

For configuration steps, see [Set up HAVRV](SETUP.md). For details about
entity behavior and thresholds, see [Features and behavior](FEATURES.md).
