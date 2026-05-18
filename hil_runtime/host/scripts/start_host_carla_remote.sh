#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./host_ssh_common.sh
source "${SCRIPT_DIR}/host_ssh_common.sh"

duckpark_host_ssh_init

if [[ -z "${DUCKPARK_HOST_PLATFORM_ROOT:-}" ]]; then
  case "${DUCKPARK_HOST_SRC_ROOT%/}" in
    */SimChip-Nexus|*/carla_web_platform)
      DUCKPARK_HOST_PLATFORM_ROOT="${DUCKPARK_HOST_SRC_ROOT%/}"
      ;;
    *)
      DUCKPARK_HOST_PLATFORM_ROOT="${DUCKPARK_HOST_SRC_ROOT%/}/SimChip-Nexus"
      ;;
  esac
fi

duckpark_host_ssh \
  DUCKPARK_HOST_PLATFORM_ROOT_VALUE="${DUCKPARK_HOST_PLATFORM_ROOT}" \
  bash -s <<'EOF'
set -euo pipefail

cd "${DUCKPARK_HOST_PLATFORM_ROOT_VALUE}"
CARLA_HEADED_EXTRA_ARGS="${CARLA_HEADED_EXTRA_ARGS:--RenderOffScreen}" \
  CARLA_HEADED_WINDOW_MODE="${CARLA_HEADED_WINDOW_MODE:-windowed}" \
  bash hil_runtime/host/scripts/start_carla_headed.sh
EOF
