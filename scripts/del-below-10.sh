#!/usr/bin/env bash
# Delete simulations whose high score is below 10 and their dependent records.

set -Eeuo pipefail

if [[ $# -eq 1 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
    printf 'Usage: sudo scripts/del-below-10.sh\n\nStop snake-lab.service first. Deletes all runs with high_score < 10,\nincluding their configurations and episode results. Runs with no recorded\nscore and runs scoring 10 or more are kept.\n'
    exit 0
fi
if [[ $# -ne 0 ]]; then
    printf '[ERROR] Usage: sudo scripts/del-below-10.sh\n' >&2
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

# Keep the server stopped so workers cannot write to runs being removed.
# The run's config JSON is deleted with the run; ON DELETE CASCADE removes
# configurations and simulation_episodes. A failed batch rolls back on disconnect.
mariadb --batch --skip-column-names "${db_name}" <<'SQL'
START TRANSACTION;
DELETE FROM simulation_runs WHERE high_score < 10;
SET @deleted_runs = ROW_COUNT();
COMMIT;
SELECT CONCAT('Deleted ', @deleted_runs,
              ' simulation runs scoring below 10 and their configurations and episode results.');
SQL
