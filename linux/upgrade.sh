#!/usr/bin/env bash
set -euo pipefail
umask 077

target_image=stockflow:1.0.4
archive=$(realpath -- "${1:-/data/stockflow-1.0.4.tar}")
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

exec 9>.upgrade.lock
flock -n 9 || { printf '已有升级任务正在运行。\n' >&2; exit 1; }

api_ready() {
    local attempt schema
    for attempt in {1..20}; do
        if schema=$(curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8000/openapi.json 2>/dev/null) &&
            [[ "$schema" == *'"/api/departments"'* ]]; then
            return 0
        fi
        sleep 1
    done
    return 1
}

current_image=$(docker compose config --images)
if [[ "$current_image" == "$target_image" ]] && api_ready; then
    printf '%s 已在运行。\n' "$target_image"
    exit 0
fi
if [[ "$current_image" != stockflow:1.0.3 || ! -f "$archive" ]]; then
    printf '请在现有 1.0.3 的 compose.yaml 旁运行脚本，并指定 1.0.4 镜像包。\n' >&2
    exit 1
fi

docker load -i "$archive"
docker image inspect "$target_image" >/dev/null

mkdir -p backups
backup_dir=$(mktemp -d "./backups/upgrade-$(date +%Y%m%d-%H%M%S)-XXXXXX")
cp -p compose.yaml "$backup_dir/compose.yaml"
database_backup=$(docker compose exec -T backend python scripts/backup.py \
    --source /data/stockflow.db --output-dir "/tmp/${backup_dir##*/}" --keep 1)
docker compose cp "backend:$database_backup" "$backup_dir/stockflow.db"
chmod 600 "$backup_dir/stockflow.db"
printf '数据库和 Compose 已备份到 %s\n' "$backup_dir"

candidate=$(mktemp ./.compose-upgrade.XXXXXX)
trap 'rm -f -- "$candidate"' EXIT
sed -E 's/^([[:space:]]*image:[[:space:]]*)stockflow:1\.0\.3([[:space:]]*)$/\1stockflow:1.0.4\2/' compose.yaml >"$candidate"
if [[ "$(docker compose -f "$candidate" config --images)" != "$target_image" ]]; then
    printf '无法更新 compose.yaml 中的后端镜像标签。\n' >&2
    exit 1
fi
chmod --reference=compose.yaml "$candidate"

restore_previous() {
    printf '正在恢复旧版 Compose。\n' >&2
    docker compose logs --tail 30 backend || true
    cp -p "$backup_dir/compose.yaml" compose.yaml
    docker compose up -d --no-deps backend
}

trap 'restore_previous; exit 130' INT
trap 'restore_previous; exit 143' TERM
mv -- "$candidate" compose.yaml

if ! { docker compose up -d --no-deps backend && api_ready; }; then
    printf '新版启动或接口检查失败。\n' >&2
    restore_previous
    exit 1
fi
trap - INT TERM
printf '已升级到 %s，组织机构接口正常。\n' "$target_image"
