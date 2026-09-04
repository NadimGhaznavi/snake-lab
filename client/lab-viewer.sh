#!/usr/bin/env bash
# Run the SnakeLab live telemetry viewer from this checkout.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly PYTHON="${PROJECT_DIR}/venv/bin/python"

[[ -x "${PYTHON}" ]] || {
    printf '[ERROR] Python environment not found: %s\n' "${PYTHON}" >&2
    exit 1
}

PYTHONPATH="${PROJECT_DIR}" exec "${PYTHON}" -m snake_lab.viewer "$@"
