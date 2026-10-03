#!/usr/bin/env bash
# Install Snake Lab from this checkout into /opt/prod/snakelab.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=deploy-common.sh
source "${SCRIPT_DIR}/deploy-common.sh"

require_root
require_commands \
    python3 systemctl install getent useradd usermod mktemp chmod chown mv rm rmdir \
    mariadb openssl
validate_release_checkout

[[ ! -e "${INSTALL_DIR}" ]] ||
    die "${INSTALL_DIR} already exists; use scripts/upgrade.sh."
[[ ! -e "${LEGACY_INSTALL_DIR}" ]] ||
    die "${LEGACY_INSTALL_DIR} already exists; use scripts/upgrade.sh to migrate it."

ensure_service_account
prepare_installation_directories
provision_database
deploy_application
deploy_runtime_files
"${INSTALL_DIR}/scripts/rebuild-venv.sh"

systemctl daemon-reload
systemctl enable snake-lab.service
systemctl start snake-lab.service

printf '[SUCCESS] Snake Lab installed in %s\n' "${INSTALL_DIR}"
printf '[INFO] ZeroMQ server: tcp://127.0.0.1:41970\n'
printf '[INFO] Live telemetry: tcp://127.0.0.1:41971\n'
printf '[INFO] Simulation events: tcp://127.0.0.1:41972\n'
printf '[INFO] Run the client with: lab-client\n'
