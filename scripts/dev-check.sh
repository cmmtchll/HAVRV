#!/bin/sh
set -eu

.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest
node --test tests/test_power_dashboard.mjs tests/test_config_panel.mjs
.venv/bin/python -m coverage report --include=custom_components/havrv/config_flow.py,custom_components/havrv/configuration.py --fail-under=100
.venv/bin/python scripts/quality_scale_audit.py
