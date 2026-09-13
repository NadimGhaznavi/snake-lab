#!/usr/bin/env bash
# Remove the installed SnakeLab service, database, and files.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly INSTALL_DIR="/opt/snake-lab"
readonly UNIT_FILE="/etc/systemd/system/snake-lab.service"
readonly CLIENT_FILE="/usr/local/bin/lab-client"
readonly LEGACY_VIEWER_FILE="/usr/local/bin/lab-viewer"

if [[ ${EUID} -ne 0 ]]; then
    printf '[ERROR] Run this uninstaller as root.\n' >&2
    exit 1
fi

for command in python3 mariadb systemctl getent userdel; do
    command -v "${command}" >/dev/null 2>&1 || {
        printf '[ERROR] Required command not found: %s\n' "${command}" >&2
        exit 1
    }
done

db_name=$(PYTHONPATH="${PROJECT_DIR}" python3 -c \
    'from constants.DSnakeLab import DSnakeLab; print(DSnakeLab.DB_NAME)')
if [[ ! "${db_name}" =~ ^[A-Za-z0-9_]+$ ]]; then
    printf '[ERROR] Invalid database name: %s\n' "${db_name}" >&2
    exit 1
fi

systemctl disable --now snake-lab.service 2>/dev/null || true
# Drop the database before deleting files so failures leave the installation intact.
mariadb --batch --execute="DROP DATABASE IF EXISTS \`${db_name}\`;"
rm -f -- "${UNIT_FILE}"
rm -f -- "${CLIENT_FILE}"
rm -f -- "${LEGACY_VIEWER_FILE}"
rm -rf -- "${INSTALL_DIR}"
systemctl daemon-reload
systemctl reset-failed snake-lab.service 2>/dev/null || true
if getent passwd snake-lab >/dev/null; then
    userdel snake-lab
fi

printf '[SUCCESS] SnakeLab has been uninstalled.\n'
