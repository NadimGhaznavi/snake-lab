#!/usr/bin/env bash
# Upgrade an existing SnakeLab installation from this release checkout.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=deploy-common.sh
source "${SCRIPT_DIR}/deploy-common.sh"

require_root
require_commands \
    python3 systemctl install cmp getent useradd mktemp chmod chown mv rm \
    mariadb openssl
validate_release_checkout

[[ -d "${INSTALL_DIR}" ]] ||
    die "${INSTALL_DIR} is not installed; use scripts/install.sh."
[[ -x "${INSTALL_DIR}/venv/bin/python" ]] ||
    die "Installed Python environment is missing."
[[ -f "${INSTALL_DIR}/requirements.txt" ]] ||
    die "Installed requirements.txt is missing."

requirements_changed=false
for requirements_file in \
    requirements.txt requirements-torch-cpu.txt requirements-torch-cuda.txt; do
    if ! cmp -s "${PROJECT_DIR}/${requirements_file}" \
        "${INSTALL_DIR}/${requirements_file}"; then
        requirements_changed=true
    fi
done

systemctl stop snake-lab.service
ensure_service_account
prepare_installation_directories
provision_database
deploy_application
deploy_runtime_files
remove_legacy_layout

if [[ "${requirements_changed}" == true ]]; then
    "${INSTALL_DIR}/scripts/rebuild-venv.sh"
fi

systemctl daemon-reload
systemctl restart snake-lab.service

printf '[SUCCESS] SnakeLab upgraded successfully.\n'
