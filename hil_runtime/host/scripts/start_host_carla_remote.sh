#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./host_ssh_common.sh
source "${SCRIPT_DIR}/host_ssh_common.sh"

duckpark_host_ssh_init

duckpark_host_ssh \
  DUCKPARK_HOST_SRC_ROOT_VALUE="${DUCKPARK_HOST_SRC_ROOT}" \
  bash -s <<'EOF'
set -euo pipefail

cd "${DUCKPARK_HOST_SRC_ROOT_VALUE}"
bash hil_runtime/host/scripts/start_carla_headed.sh
EOF
