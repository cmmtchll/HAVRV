# Contributing

Thanks for helping improve HAVRV. Keep changes focused, readable, typed where
useful, and consistent with Home Assistant's async integration patterns.

## Requirements

- Python `>=3.14.2,<3.15`, matching Home Assistant Core `2026.10.0`.
- Git.
- Node.js 20 or later for dashboard and management-panel tests (available on CI runners).

## Set up a development environment

From the repository root:

```console
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

## Checks

Run these before pushing code or opening/updating a pull request:

```console
ruff check .
ruff format --check .
mypy
pytest
node --test tests/test_power_dashboard.mjs tests/test_config_panel.mjs
python -m coverage report --include=custom_components/havrv/config_flow.py,custom_components/havrv/configuration.py --fail-under=100
python scripts/quality_scale_audit.py
```

The pytest configuration enforces at least 96% coverage for the integration.
The additional coverage report enforces full native-flow and shared
configuration-validator module coverage. The
quality-scale audit reports every Bronze-through-Platinum rule and whether the
current checklist assessment marks it done, exempt, or todo. A successful audit
means the checklist is complete and evidence references are valid; it does not
mean every tier is ready. The GitHub Actions summary shows unmet criteria.
When changing a rule's assessment, update
`custom_components/havrv/quality_scale.yaml` with a rationale and evidence.
When adding code, add tests for normal behavior, failure cases, and config-entry
lifecycle behavior as applicable.

## Pull requests

- On creation and every branch update, confirm that the `Validate` workflow runs
  for the latest head SHA. Push and pull-request events already trigger it; use
  its manual dispatch for the branch if no run was triggered.
- Inspect all results and failure logs, including quality-scale checks, lint,
  HACS, and Home Assistant validation (hassfest). An older successful run does
  not validate a new commit. Fix failures before reporting completion.
- Report blocked local checks and CI runs requiring approval (`action_required`),
  skipped, pending, cancelled, or unavailable as unverified, not passing.
  Never bypass approvals or weaken validation. Retry only diagnosed transient
  failures; a retry runs the original commit, not a newly pushed fix.
- Describe the user-visible behavior and any configuration or migration impact.
- Include tests and update documentation for behavior changes.
- For dashboard picture updates, render the current bundled card with synthetic
  data and review both orientations. Keep captions and the
  [image scenarios](docs/images/README.md) synchronized; do not use private
  vehicle data or hand-edit screenshots to imply unimplemented behavior.
- Keep entity IDs stable and use Home Assistant registries and translation
  patterns rather than hard-coded presentation strings.
- Do not claim a quality-scale tier until every rule for that tier and all
  lower tiers is met.

## Integration behavior contract

Follow the [mapping and configuration contract](AGENTS.md#mapping-and-configuration-contract)
for new and changed features:

- Preserve passthrough readings and supported controls, layering validation,
  problem detection, and derived insights on top without fabricating source data.
- Accept `sensor`, `number`, and `input_number` in numeric source selectors and
  submitted-value validation, including generic passthrough. Template sensors
  and numbers use those domains, not a separate `template` domain. Non-numeric
  selectors retain their appropriate domain restrictions.
- Provide documented defaults in both forms and runtime for operational options
  and thresholds; preserve overrides and legacy entries. Do not guess RV
  specifications or manufacturer-specific safety limits.
- Use the profile's selected measurement system consistently for unit-bearing
  readings, limits, and derived values, with appropriate Home Assistant unit
  metadata. Preserve explicit per-entity user overrides.
- Test source-domain support, missing defaults, overrides, unit mismatches, and
  invalid/unavailable sources and lifecycle behavior as applicable.
- Update the README and linked setup, feature, and troubleshooting guides for
  user-visible changes, and keep quality-scale rationales and evidence current.
- Every new dashboard display class must declare its default-`true` show/hide
  option, readable label and filtered model fields in `DISPLAY_CLASSES` in
  `custom_components/havrv/frontend/havrv-dashboard.js`. Reuse this declaration
  for the card editor/defaults and both strategies. Filter before summaries and
  layout so hidden classes reserve no space, count no alerts and generate no
  sections. Cover defaults, explicit false, toggling and dense layouts with
  Node tests. Do not predeclare or implement speculative future systems.

These are contributor requirements, not a claim that every existing feature
already satisfies them; user guides describe currently implemented behavior.
