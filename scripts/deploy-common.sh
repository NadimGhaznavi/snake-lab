#!/usr/bin/env bash
# Shared installation functions for SnakeLab lifecycle scripts.

readonly INSTALL_DIR="/opt/snake-lab"
readonly APP_DIR="${INSTALL_DIR}/app"
readonly UNIT_SOURCE="${PROJECT_DIR}/systemd/snake-lab.service"
readonly UNIT_DEST="/etc/systemd/system/snake-lab.service"
readonly CLIENT_DEST="/usr/local/bin/lab-client"

die() {
    printf '[ERROR] %s\n' "$*" >&2
    exit 1
}

require_root() {
    [[ ${EUID} -eq 0 ]] || die "Run this command as root."
}

require_commands() {
    local command
    for command in "$@"; do
        command -v "${command}" >/dev/null 2>&1 ||
            die "Required command not found: ${command}"
    done
}

validate_release_checkout() {
    local path
    local -a required_files=(
        "client/lab-client"
        "constants/__init__.py"
        "constants/DModule.py"
        "constants/DMyLog.py"
        "constants/DSnakeLab.py"
        "requirements.txt"
        "scripts/rebuild-venv.sh"
        "snake_lab/__init__.py"
        "snake_lab/client.py"
        "snake_lab/server.py"
        "systemd/snake-lab.service"
        "utils/__init__.py"
        "utils/MyLog.py"
    )

    for path in "${required_files[@]}"; do
        [[ -f "${PROJECT_DIR}/${path}" ]] ||
            die "Release file is missing: ${path}"
    done
}

ensure_service_account() {
    if ! getent passwd snake-lab >/dev/null; then
        useradd \
            --system \
            --user-group \
            --home-dir "${INSTALL_DIR}" \
            --shell /usr/sbin/nologin \
            snake-lab
    fi
}

prepare_installation_directories() {
    install -d -m 0755 "${INSTALL_DIR}"
    install -d -m 0755 "${INSTALL_DIR}/scripts"
    install -d -o snake-lab -g snake-lab -m 0750 "${INSTALL_DIR}/logs"
}

deploy_application() {
    local staging_dir
    staging_dir=$(mktemp -d "${INSTALL_DIR}/.app.XXXXXX")
    chmod 0755 "${staging_dir}"

    install -d -m 0755 \
        "${staging_dir}/client" \
        "${staging_dir}/constants" \
        "${staging_dir}/snake_lab" \
        "${staging_dir}/utils"

    install -m 0755 "${PROJECT_DIR}/client/lab-client" \
        "${staging_dir}/client/lab-client"
    install -m 0644 "${PROJECT_DIR}/constants/"*.py \
        "${staging_dir}/constants/"
    install -m 0644 "${PROJECT_DIR}/snake_lab/"*.py \
        "${staging_dir}/snake_lab/"
    install -m 0644 "${PROJECT_DIR}/utils/"*.py \
        "${staging_dir}/utils/"

    rm -rf -- "${APP_DIR}"
    mv -- "${staging_dir}" "${APP_DIR}"
}

deploy_runtime_files() {
    install -m 0644 "${PROJECT_DIR}/requirements.txt" \
        "${INSTALL_DIR}/requirements.txt"
    install -m 0755 "${PROJECT_DIR}/scripts/rebuild-venv.sh" \
        "${INSTALL_DIR}/scripts/rebuild-venv.sh"
    install -m 0755 "${PROJECT_DIR}/client/lab-client" "${CLIENT_DEST}"
    install -m 0644 "${UNIT_SOURCE}" "${UNIT_DEST}"
}

remove_legacy_layout() {
    rm -rf -- \
        "${INSTALL_DIR}/client" \
        "${INSTALL_DIR}/constants" \
        "${INSTALL_DIR}/snake_lab" \
        "${INSTALL_DIR}/utils"
}
