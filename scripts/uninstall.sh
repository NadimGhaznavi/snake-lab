#!/usr/bin/env bash
# Remove the installed SnakeLab service and files.

set -Eeuo pipefail

readonly INSTALL_DIR="/opt/snake-lab"
readonly UNIT_FILE="/etc/systemd/system/snake-lab.service"
readonly CLIENT_FILE="/usr/local/bin/lab-client"

if [[ ${EUID} -ne 0 ]]; then
    printf '[ERROR] Run this uninstaller as root.\n' >&2
    exit 1
fi

for command in systemctl getent userdel; do
    command -v "${command}" >/dev/null 2>&1 || {
        printf '[ERROR] Required command not found: %s\n' "${command}" >&2
        exit 1
    }
done

systemctl disable --now snake-lab.service 2>/dev/null || true
rm -f -- "${UNIT_FILE}"
rm -f -- "${CLIENT_FILE}"
rm -rf -- "${INSTALL_DIR}"
systemctl daemon-reload
systemctl reset-failed snake-lab.service 2>/dev/null || true
if getent passwd snake-lab >/dev/null; then
    userdel snake-lab
fi

printf '[SUCCESS] SnakeLab has been uninstalled.\n'
