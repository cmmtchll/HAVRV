# Troubleshooting

HAVRV mirrors selected Home Assistant entities; start by checking each source
entity in Home Assistant. If the source itself is missing, unavailable, or
incorrect, resolve that with the integration that provides it.

## The management gear page is missing or cannot save

Restart Home Assistant after updating HAVRV and refresh the browser. The page
requires an administrator account and a normally loaded HAVRV entry; it is not
a sidebar panel. Open it from the intended profile's gear so the entry ID is
selected correctly. Disabled/error entries retain Home Assistant's native
recovery actions.

Changes in all sections remain drafts until **Apply changes** and confirmation.
Validation failures keep the draft and link to the affected section. If saved
configuration changed elsewhere, an older draft is rejected; inspect the edits,
then explicitly reload the saved configuration before trying again.

If the connection drops during Apply, re-read the saved profile before retrying:
the write may have completed. If configuration is saved but reload fails, retry
the integration reload rather than blindly applying again. The native
**Reconfigure** action and options flow are recovery alternatives. Do not run
them expecting to share an unsaved panel draft.
If the page reports that Home Assistant must restart, restart Home Assistant;
an acknowledged retry alone does not mean the entry loaded successfully.

## The tow vehicle is missing from the dashboard

Open the always-present **Tow** device in **Settings → Devices & services →
HAVRV** and turn **Towing** on. Choose Car or Trailer under **Type**, and ensure
the card/strategy's **Show tow vehicle** (`show_tow`) option is not false.
Off, unknown or unavailable towing status draws nothing; an unavailable Type
also cannot select an outline. Weight can remain unknown without hiding the
outline. Refresh the browser after updating HAVRV if the new toggle is absent.

Tow values are runtime entity controls, not fields on the management page.
They restore after normal restarts/reloads without applying profile changes.
Turning Towing off retains the selected type and weight. The switch only
records towing status; it does not operate a hitch or certify readiness.

## A mapped entity is missing

Open HAVRV's gear page, choose **System mappings** and check that the intended entity is selected in the
correct system group. System mappings accept sensors, numbers, input-number helpers, binary sensors,
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

Open **Power** on the management page and confirm the mapping for the correct
independent bank/device. The same settings remain in the native options fallback.
Only declared live mappings create entities. Numeric sources must have a
finite value and a compatible voltage/current unit; unitless helpers are
interpreted as V/A. Enabled, Charging, Warning, and Problem must report `on` or `off`.
Charging is not inferred from a negative/positive current, an enabled inverter,
shore power, a running generator, or a running engine.

Power statuses are read-only even if their source is a switch. Use the source
integration's controls directly when needed; HAVRV does not start/stop a
generator or operate battery disconnects through these entities.

For missing shore-line readings, check **Shore power line count** and select
two lines before mapping Line 2. Existing voltage/current mappings are Line 1;
new shore configurations default to two lines, but older configurations retain
one until expanded. Frequency, watts and shared energy require their own
numeric sources with compatible Hz, W and kWh units, respectively (or unitless
helpers interpreted in those units). Negative energy is unavailable. HAVRV
does not calculate missing watts/energy or connect directly to Hughes Watchdog.
Reset energy through the underlying meter/integration; its next energy reading
will be mirrored by HAVRV. There is no HAVRV energy-reset button or trip counter.

If a source section exists but its overview box is missing, choose a
placement instead of **Not shown**, and ensure `show_power` is not `false`.
Shore Power supports only left/right outside the RV. Colocated devices have
separate boxes beside the selected region, packed to avoid overlap. Reducing bank counts
removes the highest-numbered banks and their saved mappings; increasing
the count again does not restore removed configurations.

For yellow/red electrical boxes, map explicit **Warning**/**Problem** sources
in the same options wizard. Problem takes precedence over Warning, then Enabled.
If a box is dashed with a hollow dot and **No status data** tooltip, check Enabled and any mapped
alert sources for missing/unknown/unavailable states. An unavailable mapped
alert is not assumed off. Unmapped optional alerts do not require data.
Charging and current sign do not set electrical warning/problem colors.
Electrical boxes use the same subtle tints and font scale as tire labels,
not solid status-colored tiles. Hover/focus the dot for its status label.
Equipment graphics additionally use green for Enabled on, like tire shapes;
the normal-on box indicator is green too. Each placed source has its own
graphic and box; neither charging nor current direction changes its color.
Enabled is shown by color and the status dot, not a Yes/No row. Matching
equipment tags replace callout lines, and the single legend covers all devices.

## A tank reading, percentage, or status is missing

Check the tank's source selection in **Tanks** and verify that the source
reports a usable level. Volume sources require a compatible capacity to derive
**Percentage**; percentage sources do not. **Status** uses the configured
warning/problem pair or advisory defaults. Tank types are
selected explicitly; HAVRV does not identify them from entity names.

## A cleared tank still appears

Clear both the tank's capacity and its level source in **Tanks**, then apply
changes. Either field keeps a tank defined; warning/problem thresholds do not.
In 0.4.2 and later, setup/reload removes obsolete HAVRV tank sensors and empty
devices, including leftovers from older versions. After upgrading, restart Home
Assistant and refresh the browser. An unavailable source is not a removed tank.

Source entities are never deleted. A tank device with unrelated entities or
another config entry is retained, but does not appear as a tank when it has no
HAVRV tank sensors. Removal may require updating automations referencing the
removed HAVRV entities/device; re-adding may require restoring customizations.
Manually authored dashboard cards with explicit entity IDs must be edited
manually. Recorder history is not explicitly purged.

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

Boolean tire batteries (`binary_sensor`, `input_boolean`, or `switch`) must
report on for OK and off for a problem. HAVRV does not infer polarity from
the source's battery device class. Invert a low-battery alarm with a template
binary sensor before selecting it. The percentage threshold applies only to
numeric sources. Unknown, unavailable, missing, or invalid boolean readings
do not count as data present and keep the overall tire problem on.

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
  or source entity for it. Also check `show_tires`/`show_tanks` on the card or
  strategy; they default to `true`, but explicit `false` intentionally hides
  those groups and their generated sections.
- A gray wheel or tank has no pressure or percentage reading. Check its source
  entity, as described in the sections above.

### The power toggle or placed electrical devices are missing

The current card editor includes toggles for tires, tanks, placed power sources,
coach information, mapped system sections, header and legend. If these are
missing (for example, only header and legend appear), the browser
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
power-source options screens to save. Colocated devices retain separate
nonoverlapping readout boxes; **Not shown** omits a source from the
overview, not its generated device section.

Crowded drawings now keep readable dimensions and scroll inside the card rather
than shrink without limit. Scroll horizontally or vertically to see all visible
readouts, or use a wider section. `layout: auto` changes orientation with the
card width; `horizontal`/`vertical` pin it. See the
[layout presets and visibility options](DASHBOARD.md#reuse-driving-and-parked-layouts).

## You need to change or remove a source mapping

Use the integration's **Options** to change system mappings, tank selections,
tire sources, or tire limits. Removing the HAVRV config entry removes HAVRV's
devices and exposed entities, but does not remove source entities or their
integrations.

For configuration steps, see [Set up HAVRV](SETUP.md). For details about
entity behavior and thresholds, see [Features and behavior](FEATURES.md).
