#!/usr/bin/env bash
# Upgrade an existing Snake Lab installation from this release checkout.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=deploy-common.sh
source "${SCRIPT_DIR}/deploy-common.sh"

require_root
require_commands \
    python3 mariadb systemctl install cmp getent useradd usermod mktemp chmod chown mv rm rmdir
validate_release_checkout

source_dir="${INSTALL_DIR}"
relocating=false
if [[ -e "${LEGACY_INSTALL_DIR}" ]]; then
    [[ ! -e "${INSTALL_DIR}" ]] ||
        die "Both ${LEGACY_INSTALL_DIR} and ${INSTALL_DIR} exist; resolve the duplicate installations first."
    source_dir="${LEGACY_INSTALL_DIR}"
    relocating=true
fi
[[ ! -L "${source_dir}" && -d "${source_dir}" ]] ||
    die "${INSTALL_DIR} is not installed; use scripts/install.sh."
[[ -x "${source_dir}/venv/bin/python" || -f "${source_dir}/.venv-needs-rebuild" ]] ||
    die "Installed Python environment is missing."
[[ -f "${source_dir}/requirements.txt" ]] ||
    die "Installed requirements.txt is missing."
[[ -f "${source_dir}/config/database.json" ]] ||
    die "Installed database credentials are missing."

requirements_changed=false
for requirements_file in \
    requirements.txt requirements-torch-cpu.txt; do
    if ! cmp -s "${PROJECT_DIR}/${requirements_file}" \
        "${source_dir}/${requirements_file}"; then
        requirements_changed=true
    fi
done

systemctl stop snake-lab.service
if [[ "${relocating}" == true ]]; then
    install -d -m 0755 /opt/prod
    : >"${source_dir}/.venv-needs-rebuild"
    mv -- "${source_dir}" "${INSTALL_DIR}"
    # Virtual environment launchers contain absolute paths and must be rebuilt.
    requirements_changed=true
fi
apply_database_schema
ensure_service_account
prepare_installation_directories
deploy_application
deploy_runtime_files
remove_legacy_layout

if [[ "${requirements_changed}" == true || -f "${INSTALL_DIR}/.venv-needs-rebuild" ]]; then
    : >"${INSTALL_DIR}/.venv-needs-rebuild"
    "${INSTALL_DIR}/scripts/rebuild-venv.sh"
    rm -f -- "${INSTALL_DIR}/.venv-needs-rebuild"
fi

systemctl daemon-reload
systemctl restart snake-lab.service

printf '[SUCCESS] Snake Lab upgraded successfully.\n'
