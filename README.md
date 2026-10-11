# HAVRV

HAVRV is a Home Assistant custom integration that organizes existing RV-related
entities into a consistent RV profile. It does not connect to or discover RV
hardware; you select the Home Assistant entities that already represent your
systems.

> **Project status:** Early foundation. HAVRV supports RV profiles, system
entity mappings, optional tank-level monitoring, and configurable tire
monitoring. Notifications, integration-specific triggers and conditions, and
physical-device discovery are not implemented.

## Get started

Follow the [setup guide](docs/SETUP.md) to install HAVRV, add an RV profile,
choose existing entities, and configure optional tank and tire monitoring.

| I want to… | Read |
| --- | --- |
| Install and configure HAVRV | [Setup guide](docs/SETUP.md) |
| Understand entities, tire/tank behavior, and limitations | [Feature guide](docs/FEATURES.md) |
| Diagnose a setup or entity problem | [Troubleshooting](docs/TROUBLESHOOTING.md) |
| Contribute or run checks | [Contributing](CONTRIBUTING.md) |
| See the quality-scale roadmap | [Quality scale](QUALITY_SCALE.md) |

## What HAVRV does

- Keeps coach details, dimensions, tank capacities, axle layout, and wheel
  configuration on an RV device.
- Groups selected sensors, binary sensors, switches, lights, and climate
  entities under RV system devices. Sensor readings are mirrored; supported
  controls forward actions to their selected source.
- Optionally creates water-tank devices and tire devices from selected existing
  entities, with percentage/status readings, configured-limit checks, and
  comparative tire analysis.

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
