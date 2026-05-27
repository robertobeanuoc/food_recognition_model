#!/usr/bin/env bash

set -euo pipefail

BACKUP_ROOT="${1:-/mnt/naslr_home/Backup_Databases}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-}"
MYSQL_BIN="${MYSQL_BIN:-mysql}"
MYSQLDUMP_BIN="${MYSQLDUMP_BIN:-mysqldump}"

if [[ -z "${DB_PASSWORD}" ]]; then
  read -r -s -p "MySQL password: " DB_PASSWORD
  printf '\n'
fi

mkdir -p "${BACKUP_ROOT}"

timestamp="$(date +%Y%m%d_%H%M%S)"

mapfile -t databases < <(
  MYSQL_PWD="${DB_PASSWORD}" "${MYSQL_BIN}" \
    --protocol=tcp \
    -h "${DB_HOST}" \
    -P "${DB_PORT}" \
    -u "${DB_USER}" \
    -N -B \
    -e "SHOW DATABASES;" \
    | while IFS= read -r database; do
        if [[ "${database}" == "information_schema" || "${database}" == "performance_schema" || "${database}" == "mysql" || "${database}" == "sys" ]]; then
          continue
        fi

        printf '%s\n' "${database}"
      done
)

if [[ ${#databases[@]} -eq 0 ]]; then
  echo "No user databases were found on ${DB_HOST}:${DB_PORT}."
  exit 0
fi

for database in "${databases[@]}"; do
  database_dir="${BACKUP_ROOT}/${database}"
  mkdir -p "${database_dir}"

  dump_file="${database_dir}/${database}_${timestamp}.sql"

  MYSQL_PWD="${DB_PASSWORD}" "${MYSQLDUMP_BIN}" \
    --protocol=tcp \
    -h "${DB_HOST}" \
    -P "${DB_PORT}" \
    -u "${DB_USER}" \
    --single-transaction \
    --routines \
    --events \
    --triggers \
    --databases "${database}" \
    > "${dump_file}"

  echo "Backed up ${database} to ${dump_file}"
done

echo "Backups stored under ${BACKUP_ROOT}"