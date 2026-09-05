#!/usr/bin/env bash
# Install SnakeLab from this checkout into /opt/snake-lab.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=deploy-common.sh
source "${SCRIPT_DIR}/deploy-common.sh"

require_root
require_commands \
    python3 systemctl install getent useradd mktemp chmod chown mv rm \
    mariadb openssl
validate_release_checkout

[[ ! -e "${INSTALL_DIR}" ]] ||
    die "${INSTALL_DIR} already exists; use scripts/upgrade.sh."

ensure_service_account
prepare_installation_directories
provision_database
deploy_application
deploy_runtime_files
"${INSTALL_DIR}/scripts/rebuild-venv.sh"

systemctl daemon-reload
systemctl enable snake-lab.service
systemctl start snake-lab.service

printf '[SUCCESS] SnakeLab installed in %s\n' "${INSTALL_DIR}"
printf '[INFO] ZeroMQ server: tcp://127.0.0.1:41970\n'
printf '[INFO] Live telemetry: tcp://127.0.0.1:41971\n'
printf '[INFO] Simulation events: tcp://127.0.0.1:41972\n'
printf '[INFO] Run the client with: lab-client\n'
