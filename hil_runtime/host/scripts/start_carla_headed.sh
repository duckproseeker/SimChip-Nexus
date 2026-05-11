#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CARLA_HEADED_CONTAINER_NAME:-carla-headed}"
IMAGE="${CARLA_HEADED_IMAGE:-carlasim/carla:0.9.16}"
DISPLAY_VALUE="${CARLA_HEADED_DISPLAY:-${DISPLAY:-:1}}"
XAUTHORITY_PATH="${CARLA_HEADED_XAUTHORITY:-/run/user/1000/gdm/Xauthority}"
RPC_PORT="${CARLA_HEADED_RPC_PORT:-2000}"
QUALITY_LEVEL="${CARLA_HEADED_QUALITY_LEVEL:-High}"
RENDERER="${CARLA_HEADED_RENDERER:-vulkan}"
RES_X="${CARLA_HEADED_RES_X:-1920}"
RES_Y="${CARLA_HEADED_RES_Y:-1080}"
WINDOW_MODE="${CARLA_HEADED_WINDOW_MODE:-fullscreen}"
EXTRA_ARGS="${CARLA_HEADED_EXTRA_ARGS:-}"
WAIT_FOR_RPC="${CARLA_HEADED_WAIT_FOR_RPC:-1}"
WAIT_TIMEOUT_SECONDS="${CARLA_HEADED_WAIT_TIMEOUT_SECONDS:-45}"
WAIT_POLL_INTERVAL_SECONDS="${CARLA_HEADED_WAIT_POLL_INTERVAL_SECONDS:-1}"
READY_GRACE_SECONDS="${CARLA_HEADED_READY_GRACE_SECONDS:-3}"
READY_CHECK_ENABLED="${CARLA_HEADED_READY_CHECK_ENABLED:-1}"
READY_CHECK_CONTAINER="${CARLA_HEADED_READY_CHECK_CONTAINER:-ros2-dev}"
READY_CHECK_HOST="${CARLA_HEADED_READY_CHECK_HOST:-}"
READY_CHECK_PYTHON_BIN="${CARLA_HEADED_READY_CHECK_PYTHON_BIN:-python3}"
READY_CHECK_CLIENT_TIMEOUT_SECONDS="${CARLA_HEADED_READY_CHECK_CLIENT_TIMEOUT_SECONDS:-5}"
ENSURE_HOST_HDMI_MIRROR="${CARLA_HEADED_ENSURE_HOST_HDMI_MIRROR:-1}"
ENSURE_HOST_HDMI_SCRIPT="${CARLA_HEADED_ENSURE_HOST_HDMI_SCRIPT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/ensure_host_hdmi_mirror.sh}"

usage() {
  cat <<'EOF'
Usage:
  bash hil_runtime/host/scripts/start_carla_headed.sh [options]

Options:
  --container-name <name>   Docker container name, default carla-headed
  --image <image>           CARLA image, default carlasim/carla:0.9.16
  --display <display>       X11 display, default :1
  --xauthority <path>       Xauthority file path
  --rpc-port <port>         CARLA RPC port, default 2000
  --quality-level <level>   CARLA quality level, default High
  --renderer <name>         vulkan | opengl, default vulkan
  --res-x <pixels>          Window width, default 1920
  --res-y <pixels>          Window height, default 1080
  --window-mode <mode>      fullscreen | windowed, default fullscreen
  --help                    Show this help

Environment overrides:
  CARLA_HEADED_EXTRA_ARGS   Extra raw args appended to CarlaUE4.sh
  CARLA_HEADED_WAIT_FOR_RPC Wait for CARLA RPC after launch, default 1
  CARLA_HEADED_WAIT_TIMEOUT_SECONDS
                            Max seconds to wait for CARLA RPC, default 45
  CARLA_HEADED_ENSURE_HOST_HDMI_MIRROR
                            Ensure HDMI mirror is active before launch, default 1

Examples:
  bash hil_runtime/host/scripts/start_carla_headed.sh
  CARLA_HEADED_DISPLAY=:1 CARLA_HEADED_RES_X=1920 CARLA_HEADED_RES_Y=1080 \
    bash hil_runtime/host/scripts/start_carla_headed.sh
EOF
}

require_arg_value() {
  if [[ $# -lt 2 || -z "${2:-}" ]]; then
    echo "Missing value for $1" >&2
    usage >&2
    exit 1
  fi
}

while (($# > 0)); do
  case "$1" in
    --container-name)
      require_arg_value "$@"
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --image)
      require_arg_value "$@"
      IMAGE="$2"
      shift 2
      ;;
    --display)
      require_arg_value "$@"
      DISPLAY_VALUE="$2"
      shift 2
      ;;
    --xauthority)
      require_arg_value "$@"
      XAUTHORITY_PATH="$2"
      shift 2
      ;;
    --rpc-port)
      require_arg_value "$@"
      RPC_PORT="$2"
      shift 2
      ;;
    --quality-level)
      require_arg_value "$@"
      QUALITY_LEVEL="$2"
      shift 2
      ;;
    --renderer)
      require_arg_value "$@"
      RENDERER="$2"
      shift 2
      ;;
    --res-x)
      require_arg_value "$@"
      RES_X="$2"
      shift 2
      ;;
    --res-y)
      require_arg_value "$@"
      RES_Y="$2"
      shift 2
      ;;
    --window-mode)
      require_arg_value "$@"
      WINDOW_MODE="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

log() {
  printf '%s start-carla-headed %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

bool_flag() {
  local value
  value=$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')
  [[ "${value}" == "1" || "${value}" == "true" || "${value}" == "yes" || "${value}" == "on" ]]
}

carla_image_repository() {
  printf '%s\n' "${IMAGE%%:*}"
}

container_is_running() {
  local running_state
  running_state="$(docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
  [[ "${running_state}" == "true" ]]
}

named_container_is_running() {
  local container_name="$1"
  local running_state
  running_state="$(docker inspect -f '{{.State.Running}}' "${container_name}" 2>/dev/null || true)"
  [[ "${running_state}" == "true" ]]
}

print_container_logs() {
  docker logs --tail 120 "${CONTAINER_NAME}" 2>&1 || true
}

stop_conflicting_carla_containers() {
  local repository
  local running_name
  local running_image
  local conflicts=()

  repository="$(carla_image_repository)"
  while IFS=$'\t' read -r running_name running_image; do
    [[ -n "${running_name}" ]] || continue
    [[ "${running_name}" == "${CONTAINER_NAME}" ]] && continue
    if [[ "${running_image}" == "${repository}" || "${running_image}" == "${repository}:"* ]]; then
      conflicts+=("${running_name}")
    fi
  done < <(docker ps --format '{{.Names}}\t{{.Image}}')

  if [[ "${#conflicts[@]}" -eq 0 ]]; then
    return 0
  fi

  log "stopping conflicting CARLA containers: ${conflicts[*]}"
  docker rm -f "${conflicts[@]}" >/dev/null
}

detect_ready_check_host() {
  if [[ -n "${READY_CHECK_HOST}" ]]; then
    printf '%s\n' "${READY_CHECK_HOST}"
    return 0
  fi

  local detected_host
  detected_host="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -n "${detected_host}" ]]; then
    printf '%s\n' "${detected_host}"
    return 0
  fi

  printf '127.0.0.1\n'
}

ready_check_supported() {
  bool_flag "${READY_CHECK_ENABLED}" || return 1
  named_container_is_running "${READY_CHECK_CONTAINER}" || return 1
  docker exec "${READY_CHECK_CONTAINER}" "${READY_CHECK_PYTHON_BIN}" -c 'import carla' >/dev/null 2>&1
}

wait_for_rpc_port() {
  local deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
  while (( SECONDS <= deadline )); do
    if ! container_is_running; then
      echo "Headed CARLA container exited before RPC became ready" >&2
      print_container_logs >&2
      return 1
    fi
    if (echo >"/dev/tcp/127.0.0.1/${RPC_PORT}") >/dev/null 2>&1; then
      if (( READY_GRACE_SECONDS > 0 )); then
        sleep "${READY_GRACE_SECONDS}"
        if ! container_is_running; then
          echo "Headed CARLA container exited right after RPC became ready" >&2
          print_container_logs >&2
          return 1
        fi
      fi
      return 0
    fi
    sleep "${WAIT_POLL_INTERVAL_SECONDS}"
  done
  echo "Headed CARLA RPC did not become ready within ${WAIT_TIMEOUT_SECONDS}s" >&2
  print_container_logs >&2
  return 1
}

wait_for_carla_api() {
  local deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
  local ready_check_host
  ready_check_host="$(detect_ready_check_host)"

  while (( SECONDS <= deadline )); do
    if ! container_is_running; then
      echo "Headed CARLA container exited before simulator API became ready" >&2
      print_container_logs >&2
      return 1
    fi
    if ! named_container_is_running "${READY_CHECK_CONTAINER}"; then
      echo "Ready-check container is not running: ${READY_CHECK_CONTAINER}" >&2
      return 1
    fi
    if docker exec \
      -e "CARLA_READY_CHECK_HOST=${ready_check_host}" \
      -e "CARLA_READY_CHECK_PORT=${RPC_PORT}" \
      -e "CARLA_READY_CHECK_TIMEOUT=${READY_CHECK_CLIENT_TIMEOUT_SECONDS}" \
      "${READY_CHECK_CONTAINER}" \
      "${READY_CHECK_PYTHON_BIN}" \
      - <<'PY' >/dev/null 2>&1
import os

import carla

client = carla.Client(
    os.environ["CARLA_READY_CHECK_HOST"],
    int(os.environ["CARLA_READY_CHECK_PORT"]),
)
client.set_timeout(float(os.environ["CARLA_READY_CHECK_TIMEOUT"]))
world = client.get_world()
_ = world.get_map().name
try:
    world.wait_for_tick(seconds=float(os.environ["CARLA_READY_CHECK_TIMEOUT"]))
except TypeError:
    world.wait_for_tick()
PY
    then
      return 0
    fi
    sleep "${WAIT_POLL_INTERVAL_SECONDS}"
  done
  echo "Headed CARLA simulator API did not become ready within ${WAIT_TIMEOUT_SECONDS}s" >&2
  print_container_logs >&2
  return 1
}

require_command docker

if bool_flag "${ENSURE_HOST_HDMI_MIRROR}"; then
  if [[ ! -x "${ENSURE_HOST_HDMI_SCRIPT}" ]]; then
    echo "HDMI mirror helper not found: ${ENSURE_HOST_HDMI_SCRIPT}" >&2
    exit 1
  fi
  log "ensuring host HDMI mirror is active before starting headed CARLA"
  DUCKPARK_HOST_DISPLAY="${DISPLAY_VALUE}" \
    DUCKPARK_HOST_XAUTHORITY="${XAUTHORITY_PATH}" \
    bash "${ENSURE_HOST_HDMI_SCRIPT}"
fi

if [[ ! -S /tmp/.X11-unix/X0 && ! -S /tmp/.X11-unix/X1 ]]; then
  echo "No X11 socket found under /tmp/.X11-unix" >&2
  exit 1
fi

if [[ ! -f "${XAUTHORITY_PATH}" ]]; then
  echo "Xauthority file does not exist: ${XAUTHORITY_PATH}" >&2
  exit 1
fi

if [[ "${RENDERER}" != "vulkan" && "${RENDERER}" != "opengl" ]]; then
  echo "Unsupported renderer: ${RENDERER}" >&2
  exit 1
fi

if [[ "${WINDOW_MODE}" != "fullscreen" && "${WINDOW_MODE}" != "windowed" ]]; then
  echo "Unsupported window mode: ${WINDOW_MODE}" >&2
  exit 1
fi

stop_conflicting_carla_containers
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

declare -a carla_args=(
  "./CarlaUE4.sh"
  "-${RENDERER}"
  "-nosound"
  "-quality-level=${QUALITY_LEVEL}"
  "-carla-rpc-port=${RPC_PORT}"
  "-ResX=${RES_X}"
  "-ResY=${RES_Y}"
  "--ros2"
)

if [[ "${WINDOW_MODE}" == "fullscreen" ]]; then
  carla_args+=("-fullscreen")
else
  carla_args+=("-windowed")
fi

if [[ -n "${EXTRA_ARGS}" ]]; then
  # shellcheck disable=SC2206
  extra_args=( ${EXTRA_ARGS} )
  carla_args+=("${extra_args[@]}")
fi

log "starting ${CONTAINER_NAME} on DISPLAY=${DISPLAY_VALUE}, rpc=${RPC_PORT}, ${RES_X}x${RES_Y}, window_mode=${WINDOW_MODE}"

container_id="$(
  docker run -d --rm \
    --name "${CONTAINER_NAME}" \
    --runtime=nvidia \
    --net=host \
    --env DISPLAY="${DISPLAY_VALUE}" \
    --env XAUTHORITY="${XAUTHORITY_PATH}" \
    --env NVIDIA_VISIBLE_DEVICES=all \
    --env NVIDIA_DRIVER_CAPABILITIES=all \
    --volume /tmp/.X11-unix:/tmp/.X11-unix:rw \
    --volume "${XAUTHORITY_PATH}:${XAUTHORITY_PATH}:ro" \
    "${IMAGE}" \
    "${carla_args[@]}"
)"

log "container started: ${container_id}"
if bool_flag "${WAIT_FOR_RPC}"; then
  log "waiting for CARLA RPC on 127.0.0.1:${RPC_PORT}"
  if ! wait_for_rpc_port; then
    echo "CARLA RPC did not become ready within ${WAIT_TIMEOUT_SECONDS}s" >&2
    exit 1
  fi
  log "CARLA RPC ready"
  if ready_check_supported; then
    log "waiting for CARLA simulator API readiness via ${READY_CHECK_CONTAINER}"
    if ! wait_for_carla_api; then
      echo "CARLA simulator API did not become ready within ${WAIT_TIMEOUT_SECONDS}s" >&2
      exit 1
    fi
    log "CARLA simulator API ready"
  else
    log "ready-check container unavailable, falling back to RPC-port readiness only"
  fi
fi
log "follow logs with: docker logs -f ${CONTAINER_NAME}"
