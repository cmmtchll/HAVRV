# Copilot instructions

Follow the repository-wide guidance in [`AGENTS.md`](../AGENTS.md). HAVRV is a
Home Assistant custom integration targeting Core `2026.10.0` and Python
`3.14.2`; keep implementation aligned with HA async, config-entry, entity,
translation, and testing patterns.

Before implementing or changing an integration feature, inspect relevant
source and tests, keep the change narrowly scoped, and add lifecycle/failure
tests where applicable. Do not assume RV systems or entity IDs are uniform.
Use the `ha-integration-development` skill for integration-specific work.
Consult `QUALITY_SCALE.md` before representing a quality tier as achieved.

Apply the mapping and configuration contract in `AGENTS.md` to every integration
change: passthrough first, numeric sensor/number/input-number and template sources,
aligned selector and runtime validation, documented form/runtime defaults, and
the user's profile-selected units for readings and derived values.

Before pushing code, run the complete checks in `CONTRIBUTING.md`, including
strict typing, coverage gates, and the quality-scale audit. On PR creation and
each update, inspect `Validate` runs for the latest head SHA; dispatch the existing
workflow if none was triggered. Check results and failure logs rather than
assuming a push or PR creation passed validation. Report blocked checks and
`action_required` as unverified, and never claim a medallion from audit success.
Keep linked user guides and quality-scale evidence synchronized with changes.
