#!/usr/bin/env bash
# Dump the local SnakeLab database into the current directory.

set -Eeuo pipefail
umask 077

readonly OUTPUT="$(date +'%Y-%m-%d_%H:%M')-snakelab-db.dump"

# Refuse to overwrite a backup created in the same minute.
set -o noclobber
exec 3>"${OUTPUT}"
trap 'rm -f -- "${OUTPUT}"' EXIT

mariadb-dump --user=root --protocol=socket --single-transaction --quick \
    --routines --events --triggers --databases snakelab >&3
exec 3>&-

trap - EXIT
printf 'Backup saved to %s/%s\n' "${PWD}" "${OUTPUT}"
