#!/usr/bin/env bash
# Shared installation functions for SnakeLab lifecycle scripts.

readonly INSTALL_DIR="/opt/snake-lab"
readonly APP_DIR="${INSTALL_DIR}/app"
readonly UNIT_SOURCE="${PROJECT_DIR}/systemd/snake-lab.service"
readonly UNIT_DEST="/etc/systemd/system/snake-lab.service"
readonly CLIENT_DEST="/usr/local/bin/lab-client"
readonly LEGACY_VIEWER_DEST="/usr/local/bin/lab-viewer"

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
        "constants/DNNet.py"
        "constants/DSnakeLab.py"
        "constants/DTrainer.py"
        "requirements.txt"
        "requirements-torch-cpu.txt"
        "requirements-torch-cuda.txt"
        "scripts/rebuild-venv.sh"
        "snake_lab/__init__.py"
        "snake_lab/board.py"
        "snake_lab/client.py"
        "snake_lab/configuration.py"
        "snake_lab/control_client.py"
        "snake_lab/memory.py"
        "snake_lab/model.py"
        "snake_lab/protocol.py"
        "snake_lab/runtime_control.py"
        "snake_lab/schemas/simulation-config-v1.schema.json"
        "snake_lab/server.py"
        "snake_lab/simulator.py"
        "snake_lab/telemetry.py"
        "snake_lab/telemetry_zmq.py"
        "snake_lab/trainer.py"
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
    install -d -o root -g snake-lab -m 0750 "${INSTALL_DIR}/config"
    install -d -o snake-lab -g snake-lab -m 0750 "${INSTALL_DIR}/logs"
}

provision_database() {
    local credentials_file db_host db_name db_password db_user

    credentials_file=$(PYTHONPATH="${PROJECT_DIR}" python3 -c \
        'from constants.DSnakeLab import DSnakeLab; print(DSnakeLab.DB_CREDENTIALS_FILE)')
    db_host=$(PYTHONPATH="${PROJECT_DIR}" python3 -c \
        'from constants.DSnakeLab import DSnakeLab; print(DSnakeLab.DB_HOST)')
    db_name=$(PYTHONPATH="${PROJECT_DIR}" python3 -c \
        'from constants.DSnakeLab import DSnakeLab; print(DSnakeLab.DB_NAME)')
    db_user=$(PYTHONPATH="${PROJECT_DIR}" python3 -c \
        'from constants.DSnakeLab import DSnakeLab; print(DSnakeLab.DB_USER)')

    [[ "${credentials_file}" == "${INSTALL_DIR}/config/database.json" ]] ||
        die "Database credentials file must be inside ${INSTALL_DIR}/config."
    [[ "${db_host}" =~ ^[A-Za-z0-9_.-]+$ ]] ||
        die "Invalid database host: ${db_host}"
    [[ "${db_name}" =~ ^[A-Za-z0-9_]+$ ]] ||
        die "Invalid database name: ${db_name}"
    [[ "${db_user}" =~ ^[A-Za-z0-9_]+$ ]] ||
        die "Invalid database user: ${db_user}"

    if [[ -f "${credentials_file}" ]]; then
        db_password=$(python3 -c \
            'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["password"])' \
            "${credentials_file}")
    else
        db_password=$(openssl rand -hex 32)
        printf '{"password":"%s"}\n' "${db_password}" >"${credentials_file}"
        chown root:snake-lab "${credentials_file}"
        chmod 0640 "${credentials_file}"
    fi

    [[ "${db_password}" =~ ^[0-9a-f]{64}$ ]] ||
        die "Invalid database password in ${credentials_file}."

    mariadb --batch <<SQL
CREATE DATABASE IF NOT EXISTS \`${db_name}\`
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${db_user}'@'${db_host}'
    IDENTIFIED BY '${db_password}';
ALTER USER '${db_user}'@'${db_host}' IDENTIFIED BY '${db_password}';
GRANT ALL PRIVILEGES ON \`${db_name}\`.* TO '${db_user}'@'${db_host}';
SQL
}

deploy_application() {
    local staging_dir
    staging_dir=$(mktemp -d "${INSTALL_DIR}/.app.XXXXXX")
    chmod 0755 "${staging_dir}"

    install -d -m 0755 \
        "${staging_dir}/constants" \
        "${staging_dir}/snake_lab" \
        "${staging_dir}/snake_lab/schemas" \
        "${staging_dir}/utils"

    install -m 0644 "${PROJECT_DIR}/constants/"*.py \
        "${staging_dir}/constants/"
    install -m 0644 "${PROJECT_DIR}/snake_lab/"*.py \
        "${staging_dir}/snake_lab/"
    install -m 0644 "${PROJECT_DIR}/snake_lab/schemas/"*.json \
        "${staging_dir}/snake_lab/schemas/"
    install -m 0644 "${PROJECT_DIR}/utils/"*.py \
        "${staging_dir}/utils/"

    rm -rf -- "${APP_DIR}"
    mv -- "${staging_dir}" "${APP_DIR}"
}

deploy_runtime_files() {
    install -m 0644 "${PROJECT_DIR}/requirements.txt" \
        "${INSTALL_DIR}/requirements.txt"
    install -m 0644 \
        "${PROJECT_DIR}/requirements-torch-cpu.txt" \
        "${PROJECT_DIR}/requirements-torch-cuda.txt" \
        "${INSTALL_DIR}/"
    install -m 0755 "${PROJECT_DIR}/scripts/rebuild-venv.sh" \
        "${INSTALL_DIR}/scripts/rebuild-venv.sh"
    install -m 0755 "${PROJECT_DIR}/client/lab-client" "${CLIENT_DEST}"
    rm -f -- "${LEGACY_VIEWER_DEST}"
    install -m 0644 "${UNIT_SOURCE}" "${UNIT_DEST}"
}

remove_legacy_layout() {
    rm -rf -- \
        "${INSTALL_DIR}/client" \
        "${INSTALL_DIR}/constants" \
        "${INSTALL_DIR}/snake_lab" \
        "${INSTALL_DIR}/utils"
}
