#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly PYTHON="${PROJECT_DIR}/venv/bin/python"

[[ -x "${PYTHON}" ]] || {
    printf '[ERROR] Python environment not found: %s\n' "${PYTHON}" >&2
    exit 1
}

cd -- "${PROJECT_DIR}"
exec "${PYTHON}" -m snake_lab.client "$@"
