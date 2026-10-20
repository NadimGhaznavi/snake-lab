#!/usr/bin/env bash
# Validate listener configuration before restarting the installed service.
set -Eeuo pipefail
readonly INSTALL_DIR="/opt/prod/snakelab"
[[ ${EUID} -eq 0 ]] || { printf '[ERROR] Run this command as root.\n' >&2; exit 1; }
cd -- "${INSTALL_DIR}"
PYTHONPATH="${INSTALL_DIR}" "${INSTALL_DIR}/venv/bin/python" \
    -m snakelab.NetworkConfiguration --path "${INSTALL_DIR}/conf/snakelab.json"
systemctl restart snake-lab.service
