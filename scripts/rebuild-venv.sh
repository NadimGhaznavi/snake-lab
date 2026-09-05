#!/usr/bin/env bash
# Rebuild only the SnakeLab Python virtual environment.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly VENV_DIR="${PROJECT_DIR}/venv"
readonly REQUIREMENTS="${PROJECT_DIR}/requirements.txt"
readonly TORCH_CPU_REQUIREMENTS="${PROJECT_DIR}/requirements-torch-cpu.txt"

command -v python3 >/dev/null 2>&1 || {
    printf '[ERROR] Required command not found: python3\n' >&2
    exit 1
}
[[ -f "${REQUIREMENTS}" ]] || {
    printf '[ERROR] Requirements file not found: %s\n' "${REQUIREMENTS}" >&2
    exit 1
}
[[ -f "${TORCH_CPU_REQUIREMENTS}" ]] || {
    printf '[ERROR] Requirements file not found: %s\n' \
        "${TORCH_CPU_REQUIREMENTS}" >&2
    exit 1
}

printf '[INFO] Building virtual environment from %s\n' "${REQUIREMENTS}"
rm -rf -- "${VENV_DIR}"
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install --requirement "${REQUIREMENTS}"
printf '[INFO] Installing PyTorch runtime: CPU\n'
"${VENV_DIR}/bin/python" -m pip install --requirement "${TORCH_CPU_REQUIREMENTS}"

printf '[SUCCESS] Virtual environment rebuilt at %s\n' "${VENV_DIR}"
