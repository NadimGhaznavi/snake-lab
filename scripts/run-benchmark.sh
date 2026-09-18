#!/usr/bin/env bash
# Run a benchmark using the installed Python environment.
set -Eeuo pipefail
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=deploy-common.sh
source "${SCRIPT_DIR}/deploy-common.sh"
readonly PYTHON="${INSTALL_DIR}/venv/bin/python"
[[ -x "${PYTHON}" ]] || die "Installed Python environment not found: ${PYTHON}"
exec "${PYTHON}" "${SCRIPT_DIR}/run-benchmark.py" "$@"
