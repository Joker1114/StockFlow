#!/usr/bin/env bash
set -euo pipefail
umask 077

deploy_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
env_file="$deploy_dir/stockflow.env"

if [[ -e "$env_file" ]]; then
    printf 'Using existing %s\n' "$env_file"
    exit 0
fi

IFS= read -r -s -p 'Set the initial admin password (10 to 256 characters): ' password
printf '\n'
if (( ${#password} < 10 || ${#password} > 256 )); then
    printf 'Password must be 10 to 256 characters.\n' >&2
    exit 1
fi

secret="$(od -An -N32 -tx1 /dev/urandom | tr -d '[:space:]')"
temp_file="$(mktemp -- "$env_file.XXXXXX")"
trap 'rm -f -- "$temp_file"' EXIT
printf '%s\n' \
    'STOCKFLOW_ADMIN_USERNAME=admin' \
    "STOCKFLOW_ADMIN_PASSWORD=$password" \
    "STOCKFLOW_JWT_SECRET=$secret" \
    'STOCKFLOW_TOKEN_HOURS=24' > "$temp_file"
ln -T -- "$temp_file" "$env_file"
printf 'Created %s\n' "$env_file"
