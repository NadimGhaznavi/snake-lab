#!/usr/bin/env bash
# Install SnakeLab from this checkout into /opt/snake-lab.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly INSTALL_DIR="/opt/snake-lab"
readonly UNIT_SOURCE="${PROJECT_DIR}/systemd/snake-lab.service"
readonly UNIT_DEST="/etc/systemd/system/snake-lab.service"

if [[ ${EUID} -ne 0 ]]; then
    printf '[ERROR] Run this installer as root.\n' >&2
    exit 1
fi

for command in python3 systemctl install ln; do
    command -v "${command}" >/dev/null 2>&1 || {
        printf '[ERROR] Required command not found: %s\n' "${command}" >&2
        exit 1
    }
done

[[ -f "${PROJECT_DIR}/requirements.txt" ]] || {
    printf '[ERROR] requirements.txt is missing from the checkout.\n' >&2
    exit 1
}
[[ -f "${UNIT_SOURCE}" ]] || {
    printf '[ERROR] systemd unit is missing: %s\n' "${UNIT_SOURCE}" >&2
    exit 1
}

install -d -m 0755 "${INSTALL_DIR}/snake_lab"
install -d -m 0755 "${INSTALL_DIR}/constants"
install -d -m 0755 "${INSTALL_DIR}/client"
install -d -m 0755 "${INSTALL_DIR}/scripts"
install -m 0644 "${PROJECT_DIR}/snake_lab/__init__.py" "${INSTALL_DIR}/snake_lab/__init__.py"
install -m 0644 "${PROJECT_DIR}/snake_lab/server.py" "${INSTALL_DIR}/snake_lab/server.py"
install -m 0644 "${PROJECT_DIR}/snake_lab/client.py" "${INSTALL_DIR}/snake_lab/client.py"
install -m 0644 "${PROJECT_DIR}/constants/__init__.py" "${INSTALL_DIR}/constants/__init__.py"
install -m 0644 "${PROJECT_DIR}/constants/DSnakeLab.py" "${INSTALL_DIR}/constants/DSnakeLab.py"
install -m 0644 "${PROJECT_DIR}/requirements.txt" "${INSTALL_DIR}/requirements.txt"
install -m 0755 "${PROJECT_DIR}/scripts/rebuild-venv.sh" "${INSTALL_DIR}/scripts/rebuild-venv.sh"
install -m 0755 "${PROJECT_DIR}/client/lab-client.sh" "${INSTALL_DIR}/client/lab-client.sh"
ln -sfn -- "${INSTALL_DIR}/client/lab-client.sh" "/usr/local/bin/lab-client"
install -m 0644 "${UNIT_SOURCE}" "${UNIT_DEST}"

if [[ ! -x "${INSTALL_DIR}/venv/bin/python" ]]; then
    "${INSTALL_DIR}/scripts/rebuild-venv.sh"
fi
"${INSTALL_DIR}/venv/bin/python" -c 'import zmq' >/dev/null 2>&1 || {
    printf '[ERROR] Production venv is missing required modules.\n' >&2
    printf '[ERROR] Run %s/scripts/rebuild-venv.sh and reinstall.\n' "${INSTALL_DIR}" >&2
    exit 1
}

systemctl daemon-reload
systemctl enable snake-lab.service
systemctl restart snake-lab.service

printf '[SUCCESS] SnakeLab installed in %s\n' "${INSTALL_DIR}"
printf '[INFO] ZeroMQ server: tcp://127.0.0.1:41970\n'
printf '[INFO] Run the client with: lab-client\n'
