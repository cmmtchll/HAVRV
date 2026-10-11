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
   Apply `AGENTS.md`'s passthrough-first mapping contract: numeric sources accept
   sensors, numbers, input numbers, and template-backed entities in their actual
   domains, with matching flow validation and runtime support.
4. Follow config-entry lifecycle and entity-registry patterns. Use stable
   unique IDs, `has_entity_name`, translations, and appropriate entity
   metadata as features are implemented.
5. Handle unavailable sources without noisy repeated logs. Surface actionable
   configuration failures and never silently hide unexpected errors.
6. Add tests for normal behavior, invalid input, duplicate configuration,
   setup/unload, and failure recovery as applicable.
   Include helper/template sources, runtime defaults for omitted/legacy options,
   explicit overrides, and mismatched source/profile/Home Assistant units.
   Keep advisory diagnostics separate from source readings and honor the user's
   profile measurement system for unit-bearing readings and derived values.
7. Update user documentation and quality-scale tracking when behavior changes.
   Document accepted source domains, defaults, units, and advisory limitations in
   the linked setup, feature, and troubleshooting guides as applicable.
8. Before pushing code, run all checks in `CONTRIBUTING.md`, including Ruff,
   mypy, pytest, both coverage gates, and the quality-scale audit. Report any
   environment-blocked check as unverified.
9. On PR creation and every update, confirm `Validate` runs against the latest
   head SHA; dispatch it for the branch if no run was triggered. Inspect results
   and failure logs, including HACS and hassfest. Treat `action_required` and
   other incomplete checks as unverified; never bypass approvals or checks.

## Quality-scale guardrail

The project targets Silver/Gold, but a tier must not be represented as achieved
until every applicable rule at that tier and all lower tiers is implemented,
documented, and verified. For discovery rules, decide applicability based on
this integration's virtual/entity-mapping role rather than forcing a physical
device model.
