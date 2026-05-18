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
DISPLAY_WAIT_FOR_ROLE_SECONDS="${DUCKPARK_HIL_DISPLAY_WAIT_FOR_ROLE_SECONDS:-${DUCKPARK_HIL_TIMEOUT_SECONDS:-86400}}"
SENSOR_CONFIG_PATH="${DUCKPARK_HIL_SENSOR_CONFIG_PATH:-configs/sensors/front_rgb.yaml}"

duckpark_host_ssh \
  DUCKPARK_HOST_PLATFORM_ROOT_VALUE="${DUCKPARK_HOST_PLATFORM_ROOT}" \
  DUCKPARK_PLATFORM_ROOT_VALUE="${DUCKPARK_PLATFORM_ROOT:-/ros2_ws/src/SimChip-Nexus}" \
  DUCKPARK_HIL_MAP_NAME_VALUE="${DUCKPARK_HIL_MAP_NAME:-Town01}" \
  DUCKPARK_HIL_SENSOR_CONFIG_PATH_VALUE="${SENSOR_CONFIG_PATH}" \
  DUCKPARK_HIL_DISPLAY_WAIT_FOR_ROLE_SECONDS_VALUE="${DISPLAY_WAIT_FOR_ROLE_SECONDS}" \
  bash -s <<'EOF'
set -euo pipefail

cd "${DUCKPARK_HOST_PLATFORM_ROOT_VALUE}"
CARLA_FRONT_RGB_PREVIEW_BACKGROUND=1 \
  CARLA_FRONT_RGB_PREVIEW_SRC_ROOT="${DUCKPARK_PLATFORM_ROOT_VALUE}" \
  CARLA_FRONT_RGB_PREVIEW_PLATFORM_ROOT="${DUCKPARK_PLATFORM_ROOT_VALUE}" \
  CARLA_FRONT_RGB_PREVIEW_PYTHONPATH="${DUCKPARK_PLATFORM_ROOT_VALUE}" \
  bash hil_runtime/host/scripts/start_carla_front_rgb_preview.sh \
  --display-mode sensor_preview \
  --sensor-config "${DUCKPARK_HIL_SENSOR_CONFIG_PATH_VALUE}" \
  --map-name "${DUCKPARK_HIL_MAP_NAME_VALUE}" \
  --no-follow-spectator \
  --no-spawn-ego-if-missing \
  --no-enable-autopilot \
  --traffic-vehicles 0 \
  --wait-for-role-seconds "${DUCKPARK_HIL_DISPLAY_WAIT_FOR_ROLE_SECONDS_VALUE}"
EOF
