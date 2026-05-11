#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./host_ssh_common.sh
source "${SCRIPT_DIR}/host_ssh_common.sh"

duckpark_host_ssh_init

duckpark_host_ssh \
  HOST_PREVIEW_CONTAINER_NAME_VALUE="${CARLA_FRONT_RGB_PREVIEW_CONTAINER:-ros2-dev}" \
  bash -s <<'EOF'
set -euo pipefail

docker exec "${HOST_PREVIEW_CONTAINER_NAME_VALUE}" \
  pkill -f 'python3 hil_runtime/host/scripts/carla_front_rgb_preview.py' \
  >/dev/null 2>&1 || true
EOF
