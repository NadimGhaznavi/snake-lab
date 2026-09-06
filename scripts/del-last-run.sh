#!/usr/bin/env bash
# Delete the newest simulation and its dependent database records.

set -Eeuo pipefail

if [[ $# -eq 1 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
    printf 'Usage: sudo scripts/del-last-run\n\nStop snake-lab.service first. Deletes the run with the highest database ID\nand all its episode results. An empty database is left unchanged.\n'
    exit 0
fi
if [[ $# -ne 0 ]]; then
    printf '[ERROR] Usage: sudo scripts/del-last-run\n' >&2
    exit 1
fi

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=deploy-common.sh
source "${SCRIPT_DIR}/deploy-common.sh"

require_root
require_commands python3 mariadb

db_name=$(PYTHONPATH="${PROJECT_DIR}" python3 -c \
    'from constants.DSnakeLab import DSnakeLab; print(DSnakeLab.DB_NAME)')
[[ "${db_name}" =~ ^[A-Za-z0-9_]+$ ]] || die "Invalid database name: ${db_name}"

# The caller must stop the server so its worker cannot write to this run.
# ON DELETE CASCADE on fk_episode_run removes every associated episode.
# A failed batch exits without committing; disconnect rolls the transaction back.
mariadb --batch --skip-column-names "${db_name}" <<'SQL'
START TRANSACTION;
SET @last_id = NULL, @last_run_id = NULL;
SELECT id, run_id INTO @last_id, @last_run_id
FROM simulation_runs ORDER BY id DESC LIMIT 1 FOR UPDATE;
SELECT COUNT(*) INTO @episode_count
FROM simulation_episodes WHERE run_id = @last_run_id;
DELETE FROM simulation_runs WHERE id = @last_id;
COMMIT;
SELECT IF(@last_id IS NULL,
    'No simulation runs to delete.',
    CONCAT('Deleted simulation ', @last_run_id, ' (ID ', @last_id,
           ') and ', @episode_count, ' episode results.'));
SQL
