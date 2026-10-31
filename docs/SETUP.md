# Set up HAVRV

This guide walks through installation, adding an RV, choosing source entities,
and configuring optional tank and tire monitoring. HAVRV organizes entities
that Home Assistant already provides; it does not discover, pair with, or
control RV hardware directly.

## Before you start

- After installing any HAVRV update, restart Home Assistant and refresh the
  browser. Remove old manually added HAVRV dashboard Resources; the
  integration supplies the frontend automatically.
- Make sure Home Assistant is running and the integrations that provide your
  RV-related entities have been set up.
- Identify the sensors, numbers, input-number helpers, binary sensors, switches,
  lights, and climate entities you want to group. For tanks and tires, note the
  exact source entity and its unit, if it has one.
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
2. Enter a unique profile name and select a measurement system. Finish the
   short native dialog; no source selections or known specifications are required.
3. Open the profile's **gear button** on the HAVRV integration page. This opens
   the admin-only HAVRV management page, not the old options wizard.
4. In **RV profile**, select a Home Assistant zone if you want to record the RV's usual storage
   location.
5. If known, enter the number of rear axle assemblies and wheel arrangements.
   The axle count includes a tag axle: one means one main rear axle; two means
   one main axle plus a tag axle; three means two main axles plus a tag axle.
6. Enter the number of independent house and chassis battery banks. Each
   defaults to **1**; use **0** if absent. This counts complete banks, not
   individual batteries in series or parallel.
7. Use **Power** to select any bank, Inverter, Generator, or Shore Power directly.
   Unknown sources and capacities may remain blank. Use **Tanks**, **Tires** and
   **System mappings** for the other existing configuration.
8. Review the profile-wide draft with **Apply changes**, then confirm to save.
   Switching tabs does not save anything. **Discard** abandons the whole draft.

### The management page and drafts

All existing settings share one draft, including capacities shown in both the
profile and tank editors. Suggestions are not automatically applied: blank
optional limits and unknown specifications stay unspecified. Numeric source
pickers accept `sensor`, `number` and `input_number`; template-backed entities
appear in their resulting domains. Selectors for controls and on/off states
retain their domain restrictions.

Applying validates the complete profile and reviews removals, including devices
affected by reducing bank/axle counts. Original source entities are never
removed or changed. A saved change reloads HAVRV once; reload resets in-memory
tire analysis history. Explicit **Saved; reload failed** or an unverified reload
does not mean persistence failed; check the entry before retrying a save.

Drafts are kept only in the browser's memory. Confirm before leaving with
unsaved changes. External changes made through a number entity, native flow or
another browser invalidate an older draft rather than being overwritten.
Reload saved configuration explicitly before editing again after a conflict.
Changing measurement systems converts configured dimensions, capacities and
tire limits to preserve their physical meaning.

The native **Reconfigure** action and options flow remain recovery alternatives.
The detailed native-flow descriptions below also explain those fallback forms;
the normal gear destination is the management page. Existing supported profiles
use their existing storage and entity identities, without recreation for this UI.

The profile can store coach year, chassis manufacturer and make, builder or
converter and model, coach identifier, overall dimensions, fuel and
fresh/gray/black-water capacities, rear axle count, and rear wheel
arrangements. These are reference specifications, not live vehicle readings.
Editable dimensions and capacities use the profile's selected measurement
system, independent of Home Assistant's global unit defaults.

Older saved profiles that predate the current axle model are not migrated.
Remove and add those profiles again to use the current setup.

### Power-source configuration

Each bank is independent. Select **12**, **24** (default), or **48 V DC** as its
nominal voltage, and enter the complete bank's nominal capacity in **Ah** if
known. The 24 V default is a configuration starting point, not a detected
specification. Capacity has no default. No battery-series/parallel calculation
or remaining-energy estimate is made.

Select optional **Voltage** and **Current** sources from `sensor`, `number`,
or `input_number`. Template-backed sensors and numbers appear in their actual
domains. Bank readings describe DC; the logical inverter's readings describe
AC output, and generator/shore readings describe AC supply. Choose an
aggregate source appropriate to your installation; HAVRV does not sum
multiple physical inverters or AC legs.

For **Shore Power**, choose **1** or **2** AC lines. New shore configurations
default to **2**; saved configurations without a line count retain **1**, with
their existing voltage/current sources on **Line 1**. Expand the count when
ready to map Line 2. Each line accepts optional **Voltage**, **Amps**,
**Frequency**, and **Watts** sources. The original Voltage/Current fields
represent Line 1. Choose one shared **Energy** source for all shore power.
Sources may be sensors, numbers, or input-number helpers, including template
entities. Compatible units convert to **V**, **A**, **Hz**, **W**, and **kWh**;
unitless helpers use those respective units. These electrical units do not
change between profile measurement systems; entity-specific display overrides
remain respected.

Use existing Home Assistant entities from Hughes Watchdog or another meter;
there is no direct vendor connection. HAVRV does not derive watts from volts
and amps, sum line energy, or integrate power into energy. Energy follows the
underlying meter, including its resets; HAVRV has no energy-reset button or
local trip counter.

Changing line count refreshes the management editor. In the native options
fallback, submit the changed count to refresh the available fields, then submit
the mappings and complete the wizard to save. Reducing to one line removes
Line 2's saved mappings and HAVRV entities, never the underlying sources.

**Enabled**, bank **Charging**, and optional **Warning**/**Problem** accept
`binary_sensor`, `switch`, or `input_boolean` sources reporting `on`/`off`.
All are read-only, even when the source is a switch. Each requires its own
explicit mapping. Warning/Problem are optional for every bank and AC source;
there are no default electrical alert thresholds. The box's tire-style status
dot and subtle tint are red for Problem, then amber for Warning, then green
(on) or gray (off) for Enabled. Missing mapped statuses have a dashed outline,
hollow dot and no-data tooltip rather than appearing off. See [dashboard colors](DASHBOARD.md#electrical-box-colors).

Choose **L-Front**, **L-Mid**, **L-Rear**, **R-Front**, **R-Mid**, or **R-Rear**
to place a device on the RV overview; left/right are viewed facing forward.
Shore Power accepts **L** or **R** and is drawn outside the vehicle. Placement
defaults to **Not shown**; sources can still appear in dashboard device sections.
Placed sources have their own readout boxes near the chosen region, including
multiple banks at the same location; tire labels and other sources are avoided.
Battery, inverter and generator graphics appear on the coach, with a shore
plug outside. Graphics use green for Enabled on, gray for off, amber/red for
Warning/Problem and a dashed outline for unknown; boxes use the same on/off
colors. Enabled does not need a Yes/No row. Matching tags associate tire-sized
equipment graphics with their readouts without crossing callout lines.
One common legend covers the whole overview.

To edit these settings, open **Power** on the management page. In the native
options fallback, select **Edit power-source mappings, specifications and
placement**. All fallback wizard screens must be submitted before changes
are saved; cancelling preserves previous settings. Use **Reconfigure** to change
bank counts. Reducing a count removes the highest-numbered banks, their HAVRV
entities, and their saved source configuration. Original source entities are
never removed. Current version-3 profiles without these settings gain one
bank of each kind, 24 V nominal defaults, and no invented readings or placement.
Existing power mappings and locations continue to work without adding
Warning/Problem mappings. Leave either optional field blank to remove it;
submit all screens to save.

## 3. Map existing system entities

In **System mappings**, optionally assign entities to groups such as power, water,
chassis, climate, and location. Select the entity that actually represents
each function in your installation; names and entity IDs are not standardized
across RVs.

System mappings accept:

- `sensor`, `number`, `input_number` and `binary_sensor` entities for read-only values and states.
- `switch`, `light`, and `climate` entities for mirrored state and supported
  controls.

HAVRV creates an RV device and child devices for groups with mapped entities.
It does not rename, remove, or take ownership of the original source entities.
You can leave mappings empty and add them later on the management page.

## 4. Optionally configure water tanks

In **Tanks**, select an existing numeric source for each
fresh-water, gray-water, or black-water tank level you want to expose. Tank
types are selected explicitly; HAVRV does not infer them from entity names.
Each selection creates a tank device with a live **Level** sensor. If a
capacity is saved in the RV profile, the tank device also shows **Capacity**
and a calculated **Percentage**. A capacity alone also defines a tank; its
readings remain unavailable until a level source is selected. A percentage
source does not need a capacity to provide **Percentage**.

To remove a tank, clear **both its capacity and level source** and apply the
changes. HAVRV removes its generated tank sensors and empty device during the
reload, including leftovers from earlier versions. Thresholds alone do not
keep a tank defined. Original source entities and their devices are never
removed. Main-RV configuration controls remain available to add it again.
Device customizations may need restoring after re-adding a tank, and automations
referencing removed HAVRV entities or devices may need updating. This is not
a recorder-history purge.

You may set warning and problem percentages for a tank, but both thresholds
must be set together. Without an override, advisory defaults are **50% warning /
25% problem** for fresh water and **50% warning / 75% problem** for gray and
black water. Fresh water warns as the level falls; gray and black water warn as
the level rises. A configured tank gets a **Status** sensor with `ok`, `warning`,
or `problem`; without a usable percentage it remains unavailable. These defaults
are not vehicle-specific safety limits. Fuel-level monitoring is not
implemented, even though a fuel capacity can be stored on the profile.

## 5. Optionally configure tire monitoring

Tire positions are generated when the profile has a rear axle count. HAVRV
creates front and rear tire devices according to the configured axle and
wheel layouts. A tag axle is included when the count is greater than one.

In **Tires**, choose an existing pressure, temperature, and/or battery
source for each tire position. Sources may be `sensor`, `number`, or
`input_number` entities. These are read-only mirrors; HAVRV does not discover
or control TPMS hardware. The same battery selector also accepts `binary_sensor`,
`input_boolean`, and `switch`, including template binary sensors. Binary sensors
with device class `battery` or `problem` are alarms: on means a battery problem,
off means OK. Other boolean sources retain battery-OK semantics: on means OK,
off means a problem. MQTT low-battery binary sensors with `device_class: battery`
can be selected directly; no inverted template is needed. Boolean batteries are
mirrored as raw on/off, not percentages, and remain read-only.

Optionally select **Last received** for each tire: an existing `sensor` whose
state is a timezone-aware ISO timestamp (for example
`2026-10-31T12:00:00+00:00`). Template timestamp sensors use the same domain.
Relative text such as `6 minutes ago`, numeric ages, future timestamps and
timestamps without a timezone are not usable. Leave this mapping empty if
your TPMS does not provide it; pressure, temperature and monitoring still work.
The dashboard uses this timestamp's value, not the time Home Assistant updated
the pressure entity. It shows a compact age even while readings are available.
There is no automatic stale-time threshold or extra freshness alarm to tune.

Pressure and temperature retain their last valid values and original sample
times across reloads/restarts for historical display. An unavailable source
still makes its HAVRV reading unavailable; the card labels the retained number
**Last** and shows **Offline** on the same line. Remapping a source does not
reuse another source's retained reading. See the
[dashboard guide](DASHBOARD.md#tire-trends-and-reception-age) for sparklines,
partial availability and timestamp fallbacks.

You can set optional low/high pressure limits for front, rear, and tag tires,
plus a shared high-temperature limit and numeric low-battery limit (default 20%;
ignored for boolean sources). Configure limits
only when they are appropriate for your vehicle. Pressure and temperature
limits use the profile's measurement system (kPa and °C for metric; psi and °F
for US customary); recognized source units are converted before comparison.

When tire positions are configured, HAVRV also creates an **All Tire Monitor**
device for axle comparisons. See the [feature guide](FEATURES.md) for details
on its readings and the built-in pressure-trend predictors.

## 6. Check your setup

For optional travel readings, open the integration gear's management panel and
choose **Operations**. Select a GPS-capable `device_tracker` for RV location
and/or `sensor`, `number`, or `input_number` sources for altitude, detected speed
and detected direction of travel. Template sensors/numbers use their actual
domains. Leave unknown or unwanted sources blank; none are selected by default.
Altitude/speed sources may use any compatible declared distance/speed units.
HAVRV converts output readings to the RV profile's m/ft and km/h/mph units
(HA per-entity overrides remain available). Direction
must already be travel bearing in `°`, clockwise from north, in [0, 360).
HAVRV does not derive these readings from one another.

**Apply changes** saves and reloads the profile. Remapping retains stable
HAVRV identities; **Clear** removes a channel without deleting its source.
Native **Configure/options** offers the same four source fields as a recovery
path if the management panel cannot load; blank optional fields clear mappings.
Native **Reconfigure** changes profile details/units while preserving travel
source selections. Existing entries without these mappings need no migration.
See [Operations details](FEATURES.md#operations-device) for GPS validity and
privacy considerations.

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
- The **Tow** device is always present, with **Towing** initially off,
  **Type** initially Car, and **Weight** unknown. Edit these directly on the
  device at runtime; no profile setup or source mapping is needed.
  Weight uses the profile's kg/lb units. See [tow controls](FEATURES.md#tow-device).

For a missing or unavailable reading, check the original source entity in Home
Assistant first. The [troubleshooting guide](TROUBLESHOOTING.md) covers common
setup issues.

## 7. Optionally add the RV dashboard

HAVRV includes an RV overview card and a dashboard that draws your configured
axles, wheels, tanks, and optionally placed electrical sources. After installing
or updating HAVRV, restart Home
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
- Use the integration entry's **gear button** to open the management page.
  Edit coach details in **RV profile**, source devices in **Power**, and other
  mappings and limits in **Tanks**, **Tires**, and **System mappings**.
  **Apply changes** saves the shared draft and reloads the entry. The profile
  name stays the same.
- Native **Reconfigure** and the options flow remain recovery alternatives.
  Reconfigure edits coach details; options edit mappings and monitoring limits.
  Complete every screen of a native wizard to save; cancelling leaves saved
  settings unchanged.
- Power-source settings also reload the entry. Clearing a source removes its
  HAVRV reading, while remapping a bank's source keeps the HAVRV entity identity.
- Remove the HAVRV config entry to remove its devices and exposed entities.
  Source entities and their integrations are not removed.

See the [feature guide](FEATURES.md) for the complete behavior reference and
[troubleshooting](TROUBLESHOOTING.md) for help resolving problems.
