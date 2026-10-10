# Home Assistant integration quality scale

HAVRV is built toward the Home Assistant **Silver** and **Gold** quality tiers.
It is not currently certified at either tier. The scale applies to the
implemented integration behavior, not just repository configuration.

## Current foundation

- HACS-compatible single-integration repository layout and metadata.
- UI config flow for adding uniquely named RV profiles.
- Config-entry setup and unload lifecycle.
- Python 3.14.2 / Home Assistant Core 2026.10.0 target.
- Ruff, pytest, integration coverage threshold, and CI validation.
- End-user setup and project-status documentation.

These foundations do not mean all Bronze rules are complete. The integration
does not yet map source entities or create RV devices and virtual entities.

## Implementation gates

### Bronze

Complete and test the full config flow, uniqueness, runtime data, setup and
unload behavior, entity identity/naming conventions, dependency transparency,
and any applicable service/entity lifecycle rules. Document installation,
configuration, removal, actions, conditions, and triggers as those features
are introduced.

### Silver

Add appropriate offline/unavailable handling, rate-limited state-change
logging, reauthentication if credentials or external services are introduced,
complete configuration documentation, active ownership, and more than 95%
automated coverage across the integration.

### Gold

For this virtual integration, assess device discovery/update rules for
applicability rather than inventing a physical-device discovery mechanism.
Provide diagnostics, reconfiguration, repairs when user intervention is
needed, translated entity names/icons/exceptions, appropriate entity
categories and device classes, and detailed end-user docs with use cases and
automation examples. Add all applicable supported-function and dynamic-entity
behavior and test it.

The official rule names and current requirements are in the
[Home Assistant quality-scale checklist](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/).
Update this document as rules become implemented or are formally determined
not applicable.
