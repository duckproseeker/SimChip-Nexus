#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./host_ssh_common.sh
source "${SCRIPT_DIR}/host_ssh_common.sh"

duckpark_host_ssh_init

duckpark_host_ssh \
  HOST_CARLA_CONTAINER_NAME_VALUE="${CARLA_HEADED_CONTAINER_NAME:-carla-headed}" \
  bash -s <<'EOF'
set -euo pipefail

docker rm -f "${HOST_CARLA_CONTAINER_NAME_VALUE}" >/dev/null 2>&1 || true
EOF
