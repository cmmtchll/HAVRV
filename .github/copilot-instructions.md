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
