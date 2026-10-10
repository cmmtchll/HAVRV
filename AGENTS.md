# Repository guidance for coding agents

HAVRV is a Home Assistant custom integration that will map RV-specific source
entities into a stable, RV-oriented model. It must work with varied entity IDs
and system layouts; do not assume one RV manufacturer or a fixed entity set.

## Standards

- Target Home Assistant Core `2026.10.0` and Python `>=3.14.2,<3.15`.
- Follow PEP 8, PEP 257, Home Assistant async/config-entry conventions, and
  Ruff formatting and lint rules.
- Prefer Home Assistant helpers and registries. Keep abstractions proportional
  to actual repeated behavior; avoid speculative frameworks.
- Use type annotations and explicit error handling. Do not suppress failures
  with broad exception handlers or success-shaped fallbacks.
- Keep user-facing names and messages translatable. Keep persistent entity IDs
  stable and independent of source entity IDs where possible.
- Do not log entity state values or other potentially sensitive RV data unless
  necessary and safe.

## Change workflow

- Read the relevant code, callers, and tests before changing behavior.
- Make focused changes and add tests for both expected behavior and relevant
  failure/lifecycle cases.
- Run `ruff check .`, `ruff format --check .`, and `pytest`.
- Update README or supporting docs when user-visible behavior changes.
- Do not claim a Home Assistant quality tier until its full checklist and all
  lower-tier requirements are met. Track the target in `QUALITY_SCALE.md`.
- Keep the README clear about what is implemented versus planned.

See `.github/copilot-instructions.md` for repository-specific agent guidance
and `.github/skills/ha-integration-development/SKILL.md` for the development
workflow.
