# Home Assistant integration quality scale

HAVRV is built toward the Home Assistant **Silver** and **Gold** quality tiers.
It is not currently certified at either tier. The scale applies to the
implemented integration behavior, not just repository configuration.

## Current foundation

- HACS-compatible single-integration repository layout and metadata.
- UI config flow for adding uniquely named RV profiles with optional coach
  identity, storage zone, dimensions, tank capacities, axle/wheel details, and
  mappings from existing Home Assistant entities to RV system groups.
- Config-entry setup and unload lifecycle.
- Typed runtime data for new profiles, with support for existing name-only
  entries.
- RV and mapped-system devices, with mirrored sensors and binary sensors and
  action-forwarding switches, lights, and climate controls. Existing entries
  without mappings remain supported; entity configuration is editable through
  the options flow.
- Saved RV profile values, including dimensions, tank capacities, axle count,
  and wheel layouts, exposed as profile sensors on each RV device.
- Python 3.14.2 / Home Assistant Core 2026.10.0 target.
- Ruff, pytest, a 96% integration coverage threshold, and CI validation.
- End-user setup and project-status documentation.

These foundations do not mean all Bronze rules are complete. Mapping is
currently user-selected and limited to sensors, binary sensors, switches,
lights, and climate entities; automatic discovery, alerts, and triggers are
not implemented.

Profile setup currently excludes vehicle weight ratings, tire size/load-range
and inflation details, wheelbase/tow rating, and powertrain, generator,
electrical-service, and propane data. These remain potential future profile
fields and are not used in calculations or alerts.

## Automated validation

Home Assistant defines the quality scale as a checklist; there is no general
CI job that awards a tier. Most rules require reviewing runtime behavior,
documentation, or whether a rule applies. For Core integrations, `hassfest` reads
`quality_scale.yaml` (rule statuses are `todo`, `done`, or `exempt`) and checks
that the manifest's `quality_scale` tier has all lower-tier rules marked
complete or exempt. Its static rule validators cover config flow, runtime
data, setup failure handling, unique config entries, discovery,
reconfiguration, and strict typing. This validator runs only for integrations
inside Home Assistant Core; it skips standalone custom integrations such as
HAVRV. Therefore, the existing Home Assistant validation job does not assign
HAVRV a tier.

The `Quality scale checks` GitHub Actions job enforces the directly measurable
coverage rules: the pytest configuration requires at least 96% coverage across
the integration (above Silver's 95% threshold), and the config flow module
must have 100% coverage (Bronze). HACS validation, Home Assistant integration
validation, and Ruff lint/format checks remain separate CI jobs. Passing these
checks is not a tier certification; the remaining checklist rules still need
implementation and review.

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
