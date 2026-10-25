# HAVRV

HAVRV is a Home Assistant custom integration that organizes existing RV-related
entities into a consistent RV profile. It does not connect to or discover RV
hardware; you select the Home Assistant entities that already represent your
systems.

> **Project status:** Early foundation. HAVRV supports RV profiles, system
entity mappings, optional tank-level monitoring, and configurable tire
monitoring, and an RV overview dashboard. Notifications, integration-specific triggers and conditions, and
physical-device discovery are not implemented.

**0.4.2:** Clearing a water tank's capacity and level source now removes its
HAVRV sensors and empty device on reload, including old leftovers, so the
dashboard shows only defined tanks. Capacity-only tanks and configured tanks
with unavailable sources remain visible. Original source entities are untouched.
Update HAVRV, restart Home Assistant, and refresh the browser. Remove old
manually installed HAVRV dashboard Resources; no separate frontend installation
is needed. See [dashboard upgrade troubleshooting](docs/TROUBLESHOOTING.md#the-power-toggle-or-placed-electrical-devices-are-missing).

## Get started

Follow the [setup guide](docs/SETUP.md) to install HAVRV, add an RV profile,
choose existing entities, and configure optional tank and tire monitoring.

| I want to… | Read |
| --- | --- |
| Install and configure HAVRV | [Setup guide](docs/SETUP.md) |
| Understand entities, tire/tank behavior, and limitations | [Feature guide](docs/FEATURES.md) |
| Show the RV, tires, tanks, and electrical sources | [Dashboard guide](docs/DASHBOARD.md) |
| Diagnose a setup or entity problem | [Troubleshooting](docs/TROUBLESHOOTING.md) |
| Contribute or run checks | [Contributing](CONTRIBUTING.md) |
| See the quality-scale roadmap | [Quality scale](QUALITY_SCALE.md) |

## What HAVRV does

- Opens a dedicated management page from the integration entry's gear button,
  with profile, power, tank, tire and system-mapping editors. Changes across
  sections stay in one draft until **Apply changes**; no separate frontend
  installation or YAML is required. Initial setup asks only for a name and units.
- Keeps coach details, dimensions, tank capacities, axle layout, and wheel
  configuration on an RV device.
- Exposes editable dimensions, capacities, and tank/tire limits in the main
  RV device's **Configuration** section. Other saved profile details appear
  read-only in **Diagnostics**.
- Groups selected sensors, numbers, input-number helpers, binary sensors, switches, lights, and climate
  entities under RV system devices. Sensor readings are mirrored; supported
  controls forward actions to their selected source.
- Optionally creates water-tank devices and tire devices from selected existing
  entities, with percentage/status readings, configured-limit checks, and
  comparative tire analysis. Tire batteries accept numeric levels or boolean
  health sources (on means OK; off means a problem) in the same selector.
- Adds an Operations device with an operation-mode selector (Storage,
  Driving, Campsite full service, Campsite minimal, or Maintenance).
- Always adds a **Tow** device with runtime-editable Towing, Car/Trailer,
  and Weight controls. The overview shows the matching outline only while
  towing is on. See [tow controls](docs/FEATURES.md#tow-device).
- Creates independent house/chassis battery-bank devices (one of each by
  default), plus Inverter, Generator, and Shore Power. Configure bank voltage
  and capacity, read-only voltage/current/Enabled/Charging and optional
  Warning/Problem sources, and optional
  physical placement. See [power sources](docs/FEATURES.md#power-source-devices).
- Maps one or two shore-power AC lines (two by default for new configurations),
  with optional voltage, amps, frequency and watts per line and one shared kWh
  energy source. Existing single-line mappings stay on Line 1 until expanded.
  Hughes Watchdog readings can come from its existing Home Assistant entities;
  HAVRV does not connect to the meter or reset its energy counter.
- Includes an RV overview card and a generated RV dashboard. They draw the
  configured axles, single or dual wheels, and water tanks with live readings
  and status colors.
  Single and dual tire labels keep pressure and temperature on the same line.
  Electrical readout boxes follow your selected locations, like tire labels,
  without overlapping colocated sources. They use tire-style translucent
  tints, fonts, and status dots: green/gray for on/off, amber/red for optional
  mapped Warning/Problem, and dashed no-data outlines. Colored battery,
  inverter and generator graphics sit on the coach; the shore plug is outside.
  Equipment graphics are comparable to tire sizes; matching tags replace
  crossing callout lines. One common legend covers tires, tanks and electrical,
  and Enabled is indicated by color rather than a Yes/No row. Shore Power
  groups Line 1 on the left and Line 2 on the right, with shared Enabled and
  Energy readings in a separate Combined section. See
  [dashboard configuration and colors](docs/DASHBOARD.md).
  The guide also includes [crowded R-Rear placement examples](docs/DASHBOARD.md#placement-stress-example).
  Shared, default-on show/hide options cover tires, tanks, power, coach
  information, mapped system sections, header and legend. Reuse
  [driving/parked presets](docs/DASHBOARD.md#reuse-driving-and-parked-layouts) in
  small or large horizontal/vertical views. Hidden classes leave no alert
  counts or layout reservations; crowded drawings scroll instead of shrinking.

![HAVRV RV overview card](docs/images/dashboard-horizontal.png)

Entity IDs and system layouts differ between RVs. HAVRV does not assume a
particular manufacturer, fixed entity set, or source naming convention.
Readings and tire comparisons are advisory: follow the vehicle and tire
manufacturers' guidance.

## Project information

The integration targets Home Assistant Core `2026.10.0` and Python
`3.14.2` in the `3.14` series. See [CHANGELOG.md](CHANGELOG.md) for project
changes and [LICENSE](LICENSE) for the MIT license.

## Support

- [Report a bug or request a feature](https://github.com/cmmtchll/HAVRV/issues)
- [Home Assistant community](https://community.home-assistant.io/)
