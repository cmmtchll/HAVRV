# HAVRV

HAVRV is a Home Assistant custom integration for organizing the systems in a
recreational vehicle (RV). It is intended to connect the entities already
provided by an RV's devices and integrations, then expose a consistent,
RV-oriented model for dashboards, blueprints, automations, alerts, warnings,
and state triggers.

Every RV installation is different: systems, devices, and entity IDs vary. The
integration is designed as an abstraction layer over those differences, not as
a driver for a particular RV manufacturer or device.

> **Project status:** Early foundation. The integration can store an RV profile
> with optional coach, location, dimensions, tank capacity, and axle/wheel
> details. You can assign existing Home Assistant sensors, binary sensors,
> switches, lights, and climate entities to RV system devices. HAVRV exposes
> live read-only sensor values and forwards control actions for mapped
> switches, lights, and climate entities. Alerts and triggers are not
> implemented yet.

## Installation

### HACS

For HACS, the GitHub repository must be public and have a concise repository
description and relevant topics.

1. In HACS, open **Integrations** and select the three-dot menu.
2. Select **Custom repositories**.
3. Add `https://github.com/cmmtchll/HAVRV` with category **Integration**.
4. Find **HAVRV** in HACS and install it.
5. Restart Home Assistant, then add **HAVRV** from **Settings → Devices &
   services → Add integration**.

### Manual

1. Copy `custom_components/havrv` into the `custom_components` directory in
   your Home Assistant configuration directory.
2. Restart Home Assistant.
3. Add **HAVRV** from **Settings → Devices & services → Add integration**.

## Configuration

Add one entry for each RV and give each profile a unique name. The name is
required; vehicle details are optional and are stored in Home Assistant's
config-entry storage.

During setup, optionally assign existing Home Assistant entities to the power,
water, chassis, climate, location, or other group. HAVRV creates an RV device
and a child device for each group with mapped entities. Sensors and binary
sensors are mirrored as read-only entities; switches, lights, and climate
controls operate their selected source entities. Configure the integration
later to change the mapping. Remove the HAVRV config entry to remove its
devices and exposed entities; the source entities are not removed.

The profile can include the coach year, chassis manufacturer and make, coach
builder/converter and model, coach identifier, and a Home Assistant zone for
the RV's usual storage location. It can also hold overall height, length, and
width; fuel, fresh-water, gray-water, and black-water tank capacities; the
number of rear axles; and single/dual wheel arrangements for the main rear axle
and optional tag axle. For example, a coach could be represented as a 2003
Prevost H3-45 built or converted by Liberty as an Elegant Lady.

Configured profile values are exposed as sensors on the RV device, including
axle count, wheel configuration, tag-axle presence, and tank capacities.
Dimensions and capacities use the measurement system selected for the profile;
they are specification values and are not converted or treated as live readings.

Choose metric or US customary units. Dimensions are interpreted as meters or
feet, and capacities as liters or US gallons. Values are stored with that unit
system; the integration does not convert or verify the coach's specifications.
Only record values from a reliable source such as the coach documentation or
vehicle labels. The selected zone is stored by its Home Assistant zone entity
ID.

Potential follow-on profile fields include GVWR and per-axle GAWR for weight
planning, tire size/load range/recommended cold inflation pressure for tire
care, wheelbase and tow rating, and powertrain, generator, electrical-service,
and propane details. These are candidates for future work, not current setup
fields or safety calculations.

## Development

This repository targets Home Assistant Core `2026.10.0` and Python `3.14.2`
or newer in the `3.14` series. See [CONTRIBUTING.md](CONTRIBUTING.md) for
environment setup, tests, formatting, and validation commands. See
[QUALITY_SCALE.md](QUALITY_SCALE.md) for the Bronze-to-Platinum implementation
roadmap.

## Support

- [Report a bug or request a feature](https://github.com/cmmtchll/HAVRV/issues)
- [Home Assistant community](https://community.home-assistant.io/)

## License

HAVRV is licensed under the [MIT License](LICENSE).
