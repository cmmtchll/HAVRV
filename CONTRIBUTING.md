# Contributing

Thanks for helping improve HAVRV. Keep changes focused, readable, typed where
useful, and consistent with Home Assistant's async integration patterns.

## Requirements

- Python `>=3.14.2,<3.15`, matching Home Assistant Core `2026.10.0`.
- Git.

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

Run these before opening a pull request:

```console
ruff check .
ruff format --check .
pytest
python -m coverage report --include=custom_components/havrv/config_flow.py --fail-under=100
python scripts/quality_scale_audit.py
```

The pytest configuration enforces at least 96% coverage for the integration.
The additional coverage report enforces full config-flow module coverage. The
quality-scale audit reports every Bronze-through-Platinum rule and whether the
current checklist assessment marks it done, exempt, or todo. A successful audit
means the checklist is complete and evidence references are valid; it does not
mean every tier is ready. The GitHub Actions summary shows unmet criteria.
When changing a rule's assessment, update
`custom_components/havrv/quality_scale.yaml` with a rationale and evidence.
When adding code, add tests for normal behavior, failure cases, and config-entry
lifecycle behavior as applicable.

## Pull requests

- Describe the user-visible behavior and any configuration or migration impact.
- Include tests and update documentation for behavior changes.
- Keep entity IDs stable and use Home Assistant registries and translation
  patterns rather than hard-coded presentation strings.
- Do not claim a quality-scale tier until every rule for that tier and all
  lower tiers is met.
