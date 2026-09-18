#!/usr/bin/env bash
# Run a benchmark using this checkout's Python environment.
set -Eeuo pipefail
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/../venv/bin/python" "${SCRIPT_DIR}/run-benchmark.py" "$@"
