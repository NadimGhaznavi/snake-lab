#!/usr/bin/env bash
# Explicitly apply this release's SnakeLab database schema.

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=deploy-common.sh
source "${SCRIPT_DIR}/deploy-common.sh"

require_root
require_commands python3 mariadb
validate_release_checkout
apply_database_schema

printf '[SUCCESS] SnakeLab database schema applied.\n'
