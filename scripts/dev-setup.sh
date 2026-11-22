#!/bin/sh
set -eu

if ! command -v uv >/dev/null 2>&1; then
    echo "Install uv before running this setup: https://docs.astral.sh/uv/" >&2
    exit 1
fi

if [ ! -e .venv ]; then
    uv venv --python '>=3.14.2,<3.15' .venv
fi

if [ ! -x .venv/bin/python ]; then
    echo ".venv exists but does not contain a usable Python interpreter" >&2
    exit 1
fi

.venv/bin/python -c 'import sys; sys.exit(not ((3, 14, 2) <= sys.version_info < (3, 15)))' || {
    echo ".venv must use Python >=3.14.2,<3.15" >&2
    exit 1
}

uv pip install --python .venv/bin/python -e '.[test]'
