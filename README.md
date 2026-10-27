# HAVRV

HAVRV is a Home Assistant custom integration that organizes existing RV-related
entities into a consistent RV profile. It does not connect to or discover RV
hardware; you select the Home Assistant entities that already represent your
systems.

> **Project status:** In active development. Implemented features include RV
profiles, entity mappings, tank and tire monitoring, independent power-source
devices, runtime tow controls, a management page, and an RV overview dashboard.
Notifications, integration-specific triggers and conditions, and physical-device
discovery are not implemented. No Home Assistant quality tier is claimed.

**Current release: 0.5.3.** Tire battery alarms now follow their Home Assistant
device-class polarity, and valid boolean battery readings no longer show false
missing-data badges. Every RV has a **Tow** device with restorable
Towing, Car/Trailer, and Weight controls. The overview draws the selected tow
vehicle only while Towing is on. Recent updates also add two-line shore-power
readings and remove tank devices when both capacity and source are cleared.
See the [changelog](CHANGELOG.md) for release history.

After an update, restart Home Assistant and refresh the browser. The integration
installs its frontend automatically; remove old manually installed HAVRV
dashboard Resources. See [dashboard upgrade troubleshooting](docs/TROUBLESHOOTING.md#the-power-toggle-or-placed-electrical-devices-are-missing).

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
  health sources in the same selector. Battery/problem-class binary sensors use
  on=problem; other boolean sources use on=OK.
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
- Includes an RV overview card and a generated dashboard, with horizontal and
  vertical layouts, compact live readings, explicit status colors, and inline
  last-observed data ages when readings are missing. Placed electrical devices
  have independent tagged graphics and readout boxes; these illustrate
  placement, not wiring or active supply.
- Shares default-on visibility options across the card and dashboard strategies,
  including tow, tires, tanks, power, coach information, mapped systems, header,
  and legend. Hidden groups leave no alert counts or layout reservations.
  Crowded drawings scroll instead of shrinking without limit. See
  [dashboard configuration, colors, and layout presets](docs/DASHBOARD.md).

## Dashboard examples

The current card rendered with synthetic readings, not real vehicle data or
recommended specifications. These examples show a car while Towing is on,
two-line shore power, a mapped battery warning, and a mapped inverter problem.

![Horizontal HAVRV overview with a towed car and two-line shore power](docs/images/dashboard-horizontal.png)

<img src="docs/images/dashboard-vertical.png" alt="Vertical HAVRV overview with a towed car, water tanks, tires and independent electrical readouts" width="420">

See the [dashboard guide](docs/DASHBOARD.md#placement-stress-example) for crowded
placement examples and the [setup guide](docs/SETUP.md) to configure your own RV.

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
