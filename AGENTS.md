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

## Mapping and configuration contract

- Build on HAVRV's passthrough-first model: expose selected source readings and
  supported controls, then add validation, problem detection, and derived
  insights. Keep source readings available independently of advisory results;
  never invent readings when a source is invalid or unavailable.
- Numeric source selectors, including generic passthrough mappings, must accept
  `sensor`, `number`, and `input_number`. Template sensors and template numbers
  use their resulting entity domains; there is no separate `template` domain.
  Keep selector filters, submitted-value validation, and runtime handling aligned
  in setup and options flows. Preserve domain-specific restrictions for controls,
  binary states, zones, and other non-numeric selections.
- Give thresholds and operational configuration sensible, documented defaults
  so supported monitoring works without manual tuning. Apply the same defaults
  in forms and runtime evaluation, including legacy entries with missing options,
  and preserve explicit overrides. Do not invent RV specifications, source
  mappings, or manufacturer-specific safety limits; explain advisory defaults.
- HAVRV's user-selected profile measurement system governs its unit-bearing
  readings, thresholds, and derived values. Convert compatible source units
  consistently and set Home Assistant unit metadata so its global defaults do
  not silently override the profile choice. Explicit per-entity user overrides
  remain respected. Test differing source, profile, and Home Assistant units.
- Cover sensor/helper/template sources, omitted defaults, explicit overrides,
  invalid/unavailable sources, and reload/legacy behavior where applicable.

## Change workflow

- Read the relevant code, callers, and tests before changing behavior.
- Make focused changes and add tests for both expected behavior and relevant
  failure/lifecycle cases.
- Before pushing code, run the checks in `CONTRIBUTING.md`: Ruff lint and format,
  mypy, pytest (96% integration coverage), the 100% config-flow coverage check,
  and `python scripts/quality_scale_audit.py`. Fix failures before pushing;
  if the environment blocks a check, explicitly report it as unverified.
- On PR creation and every branch update, verify that the existing `Validate`
  workflow has runs for the latest head SHA. If no run was triggered, dispatch
  it for that branch. Inspect completion, check summaries, and failing job logs,
  including HACS, hassfest, and the Bronze-through-Platinum checklist audit.
  A run on an older commit does not validate new changes.
- Treat `action_required`, skipped, pending, cancelled, or unavailable checks as
  unverified, not passing. Report required approval or environment limitations;
  do not bypass approval or weaken checks. Retry only diagnosed transient
  failures, remembering that retries validate the original commit.
- Update README and the linked setup, feature, and troubleshooting guides as
  applicable when behavior changes, especially accepted sources, defaults,
  unit selection, advisory limitations, and migration impact.
- Do not claim a Home Assistant quality tier until its full checklist and all
  lower-tier requirements are met. Track the target in `QUALITY_SCALE.md`.
- Keep `custom_components/havrv/quality_scale.yaml` rationales and evidence
  current. A passing audit checks checklist integrity, not medallion achievement.
- Keep the README clear about what is implemented versus planned.

See `.github/copilot-instructions.md` for repository-specific agent guidance
and `.github/skills/ha-integration-development/SKILL.md` for the development
workflow.
