---
description: Python conventions for the HAVRV Home Assistant integration
applyTo: "**/*.py"
---

- Target Python `>=3.14.2,<3.15` and Home Assistant Core `2026.10.0`.
- Follow PEP 8 and PEP 257. Use Ruff for linting and formatting.
- Prefer async Home Assistant APIs and config-entry lifecycle patterns.
- Annotate public functions and meaningful runtime data; avoid unnecessary
  abstractions and casts.
- Keep imports ordered, use module docstrings, and make comments complete
  sentences ending in a period.
- Add tests for normal behavior, error handling, config flow, and setup/unload
  behavior as relevant.
