# HAVRV

HAVRV is a Home Assistant custom integration for organizing the systems in a
recreational vehicle (RV). It is intended to connect the entities already
provided by an RV's devices and integrations, then expose a consistent,
RV-oriented model for dashboards, blueprints, automations, alerts, warnings,
and state triggers.

Every RV installation is different: systems, devices, and entity IDs vary. The
integration is designed as an abstraction layer over those differences, not as
a driver for a particular RV manufacturer or device.

> **Project status:** Early foundation. The current integration lets you add a
> named RV profile. Entity mapping, virtual entities, alerts, and triggers are
> not implemented yet.

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

Add one entry for each RV and give each profile a unique name. The profile is
stored in Home Assistant's config-entry storage.

## Development

This repository targets Home Assistant Core `2026.10.0` and Python `3.14.2`
or newer in the `3.14` series. See [CONTRIBUTING.md](CONTRIBUTING.md) for
environment setup, tests, formatting, and validation commands. See
[QUALITY_SCALE.md](QUALITY_SCALE.md) for the Bronze-to-Gold implementation
roadmap.

## Support

- [Report a bug or request a feature](https://github.com/cmmtchll/HAVRV/issues)
- [Home Assistant community](https://community.home-assistant.io/)

## License

No license has been selected for this repository yet.
