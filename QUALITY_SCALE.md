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
  and wheel layouts, exposed as uniquely named sensors on each RV device.
- Explicit optional mappings for fresh-, gray-, and black-water tank levels
  create individual tank devices and expose configured capacities on those
  devices, plus percentage, optional direction-aware threshold status, and
  last-filled/last-emptied history sensors. Fuel-level devices are not
  implemented.
- An Operations device with a restorable operation-mode selector. The mode
  does not yet change problem detection.
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

## Quality-scale audit and CI

The current Home Assistant [checklist](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/)
contains 54 rules across Bronze, Silver, Gold, and Platinum. Each rule is
tracked in `custom_components/havrv/quality_scale.yaml` as `done`, `exempt`,
or `todo`, with a rationale and, for completed rules, repository evidence.
`scripts/quality_scale_audit.py` verifies that every official rule is present,
rejects unknown rules and invalid statuses, checks evidence paths, and writes
the status of every rule and cumulative tier readiness to the GitHub Actions
step summary. Rules requiring product, runtime, or documentation judgment are
explicitly assessed in the checklist; they are not inferred from a generic
static-analysis result. A `todo` means the criterion is not met. `exempt` must
include the reason it does not apply.

CI also independently runs the complete pytest suite, enforces at least 96%
coverage across the integration and 100% config-flow coverage, and runs Ruff
lint and formatting, HACS validation, and Home Assistant integration
validation. The latter is hassfest-based, but Home Assistant's own
`quality_scale.yaml` tier validator only runs for integrations in Home
Assistant Core, so it does not audit a standalone custom integration like
HAVRV. The local auditor fills that checklist-tracking gap; it does not award a
tier. A successful audit job means all rules are assessed and the other
automated checks passed, while the summary clearly shows which criteria remain
unmet and whether each cumulative tier's checklist is ready.

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
not applicable. Keep the rule catalog in `scripts/quality_scale_audit.py` in
sync with the linked official checklist when Home Assistant changes it.
