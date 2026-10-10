---
name: ha-integration-development
description: Implement or review HAVRV Home Assistant integration code, config flows, entities, translations, diagnostics, and tests using HA 2026.10 conventions.
---

# HAVRV integration development

Use this skill when adding or changing Home Assistant integration behavior.

## Workflow

1. Read `AGENTS.md`, `QUALITY_SCALE.md`, the target module, and its tests.
2. Confirm the behavior against the Home Assistant Core `2026.10.0` APIs and
   the integration quality-scale checklist.
3. Keep RV profiles and entity mappings data-driven. Never assume source
   entity IDs, device types, or RV systems are the same between installations.
4. Follow config-entry lifecycle and entity-registry patterns. Use stable
   unique IDs, `has_entity_name`, translations, and appropriate entity
   metadata as features are implemented.
5. Handle unavailable sources without noisy repeated logs. Surface actionable
   configuration failures and never silently hide unexpected errors.
6. Add tests for normal behavior, invalid input, duplicate configuration,
   setup/unload, and failure recovery as applicable.
7. Update user documentation and quality-scale tracking when behavior changes.
8. Run `ruff check .`, `ruff format --check .`, and `pytest`.

## Quality-scale guardrail

The project targets Silver/Gold, but a tier must not be represented as achieved
until every applicable rule at that tier and all lower tiers is implemented,
documented, and verified. For discovery rules, decide applicability based on
this integration's virtual/entity-mapping role rather than forcing a physical
device model.
