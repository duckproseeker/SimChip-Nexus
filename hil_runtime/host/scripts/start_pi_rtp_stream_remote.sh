#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${DUCKPARK_PI_HOST:-}"
PI_USER="${DUCKPARK_PI_USER:-}"
PI_PORT="${DUCKPARK_PI_PORT:-22}"
PI_RUNTIME_ROOT="${DUCKPARK_PI_RUNTIME_ROOT:-\$HOME/duckPark/src/hil_runtime}"
PI_LEGACY_PLATFORM_ROOT="${DUCKPARK_PI_LEGACY_PLATFORM_ROOT:-\$HOME/duckpark/carla_web_platform}"
PI_LOG_FILE="${DUCKPARK_PI_RTP_LOG_FILE:-/tmp/duckpark_pi_rtp_stream.log}"
PI_GATEWAY_AGENT_LOG_FILE="${DUCKPARK_PI_GATEWAY_AGENT_LOG_FILE:-/tmp/duckpark_pi_gateway_agent.log}"
PI_DUT_RESULT_RECEIVER_LOG_FILE="${DUCKPARK_PI_DUT_RESULT_RECEIVER_LOG_FILE:-/tmp/duckpark_pi_dut_result_receiver.log}"
PI_GATEWAY_ENV_FILE="${DUCKPARK_PI_GATEWAY_ENV_FILE:-/etc/duckpark/pi-gateway.env}"
SSH_BIN="${DUCKPARK_PI_SSH_BIN:-ssh}"
SSH_STRICT_HOST_KEY_CHECKING="${DUCKPARK_PI_SSH_STRICT_HOST_KEY_CHECKING:-accept-new}"
SSH_IDENTITY_FILE="${DUCKPARK_PI_SSH_IDENTITY_FILE:-}"

PI_HDMI_RTP_DEVICE_VALUE="${PI_HDMI_RTP_DEVICE:-/dev/video0}"
PI_HDMI_RTP_TARGET_HOST_VALUE="${PI_HDMI_RTP_TARGET_HOST:-192.168.50.2}"
PI_HDMI_RTP_TARGET_PORT_VALUE="${PI_HDMI_RTP_TARGET_PORT:-5000}"
PI_HDMI_RTP_WIDTH_VALUE="${PI_HDMI_RTP_WIDTH:-1920}"
PI_HDMI_RTP_HEIGHT_VALUE="${PI_HDMI_RTP_HEIGHT:-1080}"
PI_HDMI_RTP_FRAMERATE_VALUE="${PI_HDMI_RTP_FRAMERATE:-30}"
PI_HDMI_RTP_ENCODER_VALUE="${PI_HDMI_RTP_ENCODER:-auto}"
PI_HDMI_RTP_NETWORK_INTERFACE_VALUE="${PI_HDMI_RTP_NETWORK_INTERFACE:-eth0}"
PI_HDMI_RTP_INPUT_PIXFMT_VALUE="${PI_HDMI_RTP_INPUT_PIXFMT:-RGB3}"
PI_HDMI_RTP_FORCE_V4L2_FORMAT_VALUE="${PI_HDMI_RTP_FORCE_V4L2_FORMAT:-1}"
PI_HDMI_RTP_BITRATE_KBPS_VALUE="${PI_HDMI_RTP_BITRATE_KBPS:-8000}"
PI_HDMI_RTP_CONFIGURE_INPUT_VALUE="${PI_HDMI_RTP_CONFIGURE_INPUT:-1}"
PI_GATEWAY_ID_VALUE="${DUCKPARK_PI_GATEWAY_ID:-${PI_GATEWAY_ID:-rpi5-x1301-01}}"
PI_GATEWAY_NAME_VALUE="${DUCKPARK_PI_GATEWAY_NAME:-${PI_GATEWAY_NAME:-bench-a}}"
PI_GATEWAY_DUT_RESULT_RECEIVER_PORT_VALUE="${PI_GATEWAY_DUT_RESULT_RECEIVER_PORT:-18765}"
PI_GATEWAY_DUT_RESULT_RECEIVER_HOST_VALUE="${PI_GATEWAY_DUT_RESULT_RECEIVER_HOST:-0.0.0.0}"
PI_PLATFORM_API_BASE_URL_VALUE="${DUCKPARK_PLATFORM_BASE_URL:-${HIL_PLATFORM_BASE_URL:-}}"

usage() {
  cat <<'EOF'
Usage:
  bash hil_runtime/host/scripts/start_pi_rtp_stream_remote.sh

Required environment:
  DUCKPARK_PI_HOST                  Pi SSH host
  DUCKPARK_PI_USER                  Pi SSH user

Optional environment:
  DUCKPARK_PI_PORT                  Pi SSH port, default 22
  DUCKPARK_PI_RUNTIME_ROOT          New-layout hil_runtime root on Pi
  DUCKPARK_PI_LEGACY_PLATFORM_ROOT  Legacy platform repo root on Pi
  DUCKPARK_PI_RTP_LOG_FILE          Pi-side RTP log file path
  DUCKPARK_PI_SSH_BIN               SSH binary, default ssh
  DUCKPARK_PI_SSH_STRICT_HOST_KEY_CHECKING
                                     SSH StrictHostKeyChecking mode, default accept-new
  DUCKPARK_PI_SSH_IDENTITY_FILE     Optional SSH identity file. If unset, the wrapper will
                                     reuse ~/.ssh/id_ed25519_duckpark when present.

Pass-through Pi RTP environment:
  PI_HDMI_RTP_DEVICE
  PI_HDMI_RTP_TARGET_HOST
  PI_HDMI_RTP_TARGET_PORT
  PI_HDMI_RTP_WIDTH
  PI_HDMI_RTP_HEIGHT
  PI_HDMI_RTP_FRAMERATE
  PI_HDMI_RTP_ENCODER
  PI_HDMI_RTP_NETWORK_INTERFACE
  PI_HDMI_RTP_INPUT_PIXFMT
  PI_HDMI_RTP_FORCE_V4L2_FORMAT
  PI_HDMI_RTP_BITRATE_KBPS
  PI_HDMI_RTP_CONFIGURE_INPUT
  PI_GATEWAY_ID / DUCKPARK_PI_GATEWAY_ID
  PI_GATEWAY_NAME / DUCKPARK_PI_GATEWAY_NAME
  PI_GATEWAY_DUT_RESULT_RECEIVER_HOST
  PI_GATEWAY_DUT_RESULT_RECEIVER_PORT
  DUCKPARK_PLATFORM_BASE_URL / HIL_PLATFORM_BASE_URL

Notes:
  - This wrapper is intended for HIL orchestration commands executed from the host/container.
  - It ensures the Pi DUT result receiver, gateway heartbeat agent, and RTP sender are all running.
  - SSH key-based auth should already be configured; the script runs with BatchMode=yes.
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_text() {
  local value="$1"
  local label="$2"
  if [[ -z "${value}" ]]; then
    echo "${label} is required" >&2
    exit 1
  fi
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

require_command "${SSH_BIN}"
require_command python3
require_text "${PI_HOST}" "DUCKPARK_PI_HOST"
require_text "${PI_USER}" "DUCKPARK_PI_USER"

SSH_TARGET="${PI_USER}@${PI_HOST}"
declare -a SSH_ARGS=(
  -p "${PI_PORT}"
  -o BatchMode=yes
  -o "StrictHostKeyChecking=${SSH_STRICT_HOST_KEY_CHECKING}"
)

if [[ -z "${SSH_IDENTITY_FILE}" ]] && [[ -f "${HOME}/.ssh/id_ed25519_duckpark" ]]; then
  SSH_IDENTITY_FILE="${HOME}/.ssh/id_ed25519_duckpark"
fi

if [[ -n "${SSH_IDENTITY_FILE}" ]]; then
  SSH_ARGS+=(-i "${SSH_IDENTITY_FILE}" -o IdentitiesOnly=yes)
fi

if [[ -z "${PI_PLATFORM_API_BASE_URL_VALUE}" ]]; then
  PI_PLATFORM_API_BASE_URL_VALUE="$(
    python3 - "${PI_HOST}" <<'PY'
import socket
import sys

host = sys.argv[1]
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(2.0)
try:
    sock.connect((host, 22))
    print(f"http://{sock.getsockname()[0]}:8000")
finally:
    sock.close()
PY
  )"
fi

"${SSH_BIN}" \
  "${SSH_ARGS[@]}" \
  "${SSH_TARGET}" \
  PI_HDMI_RTP_DEVICE_VALUE="${PI_HDMI_RTP_DEVICE_VALUE}" \
  PI_HDMI_RTP_TARGET_HOST_VALUE="${PI_HDMI_RTP_TARGET_HOST_VALUE}" \
  PI_HDMI_RTP_TARGET_PORT_VALUE="${PI_HDMI_RTP_TARGET_PORT_VALUE}" \
  PI_HDMI_RTP_WIDTH_VALUE="${PI_HDMI_RTP_WIDTH_VALUE}" \
  PI_HDMI_RTP_HEIGHT_VALUE="${PI_HDMI_RTP_HEIGHT_VALUE}" \
  PI_HDMI_RTP_FRAMERATE_VALUE="${PI_HDMI_RTP_FRAMERATE_VALUE}" \
  PI_HDMI_RTP_ENCODER_VALUE="${PI_HDMI_RTP_ENCODER_VALUE}" \
  PI_HDMI_RTP_NETWORK_INTERFACE_VALUE="${PI_HDMI_RTP_NETWORK_INTERFACE_VALUE}" \
  PI_HDMI_RTP_INPUT_PIXFMT_VALUE="${PI_HDMI_RTP_INPUT_PIXFMT_VALUE}" \
  PI_HDMI_RTP_FORCE_V4L2_FORMAT_VALUE="${PI_HDMI_RTP_FORCE_V4L2_FORMAT_VALUE}" \
  PI_HDMI_RTP_BITRATE_KBPS_VALUE="${PI_HDMI_RTP_BITRATE_KBPS_VALUE}" \
  PI_HDMI_RTP_CONFIGURE_INPUT_VALUE="${PI_HDMI_RTP_CONFIGURE_INPUT_VALUE}" \
  PI_GATEWAY_ID_VALUE="${PI_GATEWAY_ID_VALUE}" \
  PI_GATEWAY_NAME_VALUE="${PI_GATEWAY_NAME_VALUE}" \
  PI_GATEWAY_DUT_RESULT_RECEIVER_PORT_VALUE="${PI_GATEWAY_DUT_RESULT_RECEIVER_PORT_VALUE}" \
  PI_GATEWAY_DUT_RESULT_RECEIVER_HOST_VALUE="${PI_GATEWAY_DUT_RESULT_RECEIVER_HOST_VALUE}" \
  PI_PLATFORM_API_BASE_URL_VALUE="${PI_PLATFORM_API_BASE_URL_VALUE}" \
  PI_RUNTIME_ROOT_VALUE="${PI_RUNTIME_ROOT}" \
  PI_LEGACY_PLATFORM_ROOT_VALUE="${PI_LEGACY_PLATFORM_ROOT}" \
  PI_LOG_FILE_VALUE="${PI_LOG_FILE}" \
  PI_GATEWAY_AGENT_LOG_FILE_VALUE="${PI_GATEWAY_AGENT_LOG_FILE}" \
  PI_DUT_RESULT_RECEIVER_LOG_FILE_VALUE="${PI_DUT_RESULT_RECEIVER_LOG_FILE}" \
  PI_GATEWAY_ENV_FILE_VALUE="${PI_GATEWAY_ENV_FILE}" \
  bash -s <<'EOF'
set -euo pipefail

export PI_HDMI_RTP_DEVICE="${PI_HDMI_RTP_DEVICE_VALUE}"
export PI_HDMI_RTP_TARGET_HOST="${PI_HDMI_RTP_TARGET_HOST_VALUE}"
export PI_HDMI_RTP_TARGET_PORT="${PI_HDMI_RTP_TARGET_PORT_VALUE}"
export PI_HDMI_RTP_WIDTH="${PI_HDMI_RTP_WIDTH_VALUE}"
export PI_HDMI_RTP_HEIGHT="${PI_HDMI_RTP_HEIGHT_VALUE}"
export PI_HDMI_RTP_FRAMERATE="${PI_HDMI_RTP_FRAMERATE_VALUE}"
export PI_HDMI_RTP_ENCODER="${PI_HDMI_RTP_ENCODER_VALUE}"
export PI_HDMI_RTP_NETWORK_INTERFACE="${PI_HDMI_RTP_NETWORK_INTERFACE_VALUE}"
export PI_HDMI_RTP_INPUT_PIXFMT="${PI_HDMI_RTP_INPUT_PIXFMT_VALUE}"
export PI_HDMI_RTP_FORCE_V4L2_FORMAT="${PI_HDMI_RTP_FORCE_V4L2_FORMAT_VALUE}"
export PI_HDMI_RTP_BITRATE_KBPS="${PI_HDMI_RTP_BITRATE_KBPS_VALUE}"
export PI_HDMI_RTP_CONFIGURE_INPUT="${PI_HDMI_RTP_CONFIGURE_INPUT_VALUE}"

RUNTIME_SCRIPT="${PI_RUNTIME_ROOT_VALUE}/pi/scripts/start_pi_hdmi_rtp_stream.sh"
RUNTIME_CONFIGURE_SCRIPT="${PI_RUNTIME_ROOT_VALUE}/pi/scripts/configure_pi_hdmi_input.sh"
RUNTIME_GATEWAY_AGENT_SCRIPT="${PI_RUNTIME_ROOT_VALUE}/pi/scripts/start_pi_gateway_agent.sh"
RUNTIME_DUT_RESULT_RECEIVER_SCRIPT="${PI_RUNTIME_ROOT_VALUE}/pi/scripts/start_pi_dut_result_receiver.sh"
LEGACY_SCRIPT="${PI_LEGACY_PLATFORM_ROOT_VALUE}/scripts/start_pi_hdmi_rtp_stream.sh"
LEGACY_CONFIGURE_SCRIPT="${PI_LEGACY_PLATFORM_ROOT_VALUE}/scripts/configure_pi_hdmi_input.sh"
LEGACY_GATEWAY_AGENT_SCRIPT="${PI_LEGACY_PLATFORM_ROOT_VALUE}/scripts/start_pi_gateway_agent.sh"
LEGACY_DUT_RESULT_RECEIVER_SCRIPT="${PI_LEGACY_PLATFORM_ROOT_VALUE}/scripts/start_pi_dut_result_receiver.sh"
LOG_FILE="${PI_LOG_FILE_VALUE}"
GATEWAY_AGENT_LOG_FILE="${PI_GATEWAY_AGENT_LOG_FILE_VALUE}"
DUT_RESULT_RECEIVER_LOG_FILE="${PI_DUT_RESULT_RECEIVER_LOG_FILE_VALUE}"
GATEWAY_ENV_FILE="${PI_GATEWAY_ENV_FILE_VALUE}"
STATE_DIR_DEFAULT="${PI_LEGACY_PLATFORM_ROOT_VALUE}/run_data/pi_gateway"

if [[ -f "${GATEWAY_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${GATEWAY_ENV_FILE}"
  set +a
fi

export PI_GATEWAY_ID="${PI_GATEWAY_ID_VALUE:-${PI_GATEWAY_ID:-}}"
export PI_GATEWAY_NAME="${PI_GATEWAY_NAME_VALUE:-${PI_GATEWAY_NAME:-}}"
export PI_GATEWAY_API_BASE_URL="${PI_PLATFORM_API_BASE_URL_VALUE:-${PI_GATEWAY_API_BASE_URL:-}}"
export PI_GATEWAY_DUT_RESULT_RECEIVER_PORT="${PI_GATEWAY_DUT_RESULT_RECEIVER_PORT_VALUE:-${PI_GATEWAY_DUT_RESULT_RECEIVER_PORT:-}}"
export PI_GATEWAY_DUT_RESULT_RECEIVER_HOST="${PI_GATEWAY_DUT_RESULT_RECEIVER_HOST_VALUE:-${PI_GATEWAY_DUT_RESULT_RECEIVER_HOST:-}}"
export PI_GATEWAY_STATE_DIR="${PI_GATEWAY_STATE_DIR:-${STATE_DIR_DEFAULT}}"
export PI_GATEWAY_DUT_RESULT_FILE="${PI_GATEWAY_DUT_RESULT_FILE:-${PI_GATEWAY_STATE_DIR}/dut_result.json}"
mkdir -p "${PI_GATEWAY_STATE_DIR}"

start_background_script() {
  local script_path="$1"
  local log_path="$2"
  shift 2
  nohup bash "${script_path}" "$@" >"${log_path}" 2>&1 < /dev/null &
}

start_python_module() {
  local project_root="$1"
  local module_name="$2"
  local log_path="$3"
  shift 3
  nohup env PROJECT_ROOT="${project_root}" PYTHONPATH="${project_root}:${PYTHONPATH:-}" \
    python3 -m "${module_name}" "$@" >"${log_path}" 2>&1 < /dev/null &
}

if ! pgrep -f '[d]ut_result_receiver' >/dev/null 2>&1; then
  if [[ -x "${RUNTIME_DUT_RESULT_RECEIVER_SCRIPT}" ]]; then
    start_background_script "${RUNTIME_DUT_RESULT_RECEIVER_SCRIPT}" "${DUT_RESULT_RECEIVER_LOG_FILE}"
  elif [[ -x "${LEGACY_DUT_RESULT_RECEIVER_SCRIPT}" ]]; then
    start_background_script "${LEGACY_DUT_RESULT_RECEIVER_SCRIPT}" "${DUT_RESULT_RECEIVER_LOG_FILE}"
  else
    start_python_module \
      "${PI_LEGACY_PLATFORM_ROOT_VALUE}" \
      "app.hil.dut_result_receiver" \
      "${DUT_RESULT_RECEIVER_LOG_FILE}" \
      --host "${PI_GATEWAY_DUT_RESULT_RECEIVER_HOST}" \
      --port "${PI_GATEWAY_DUT_RESULT_RECEIVER_PORT}" \
      --state-dir "${PI_GATEWAY_STATE_DIR}" \
      --result-file "${PI_GATEWAY_DUT_RESULT_FILE}"
  fi
fi

if ! pgrep -f '[g]ateway_agent' >/dev/null 2>&1; then
  if [[ -x "${RUNTIME_GATEWAY_AGENT_SCRIPT}" ]]; then
    start_background_script \
      "${RUNTIME_GATEWAY_AGENT_SCRIPT}" \
      "${GATEWAY_AGENT_LOG_FILE}" \
      --api-base-url "${PI_GATEWAY_API_BASE_URL}" \
      --gateway-id "${PI_GATEWAY_ID}" \
      --gateway-name "${PI_GATEWAY_NAME}" \
      --input-video-device "${PI_HDMI_RTP_DEVICE}"
  elif [[ -x "${LEGACY_GATEWAY_AGENT_SCRIPT}" ]]; then
    start_background_script \
      "${LEGACY_GATEWAY_AGENT_SCRIPT}" \
      "${GATEWAY_AGENT_LOG_FILE}" \
      --api-base-url "${PI_GATEWAY_API_BASE_URL}" \
      --gateway-id "${PI_GATEWAY_ID}" \
      --gateway-name "${PI_GATEWAY_NAME}" \
      --input-video-device "${PI_HDMI_RTP_DEVICE}"
  else
    start_python_module \
      "${PI_LEGACY_PLATFORM_ROOT_VALUE}" \
      "app.hil.gateway_agent" \
      "${GATEWAY_AGENT_LOG_FILE}" \
      --api-base-url "${PI_GATEWAY_API_BASE_URL}" \
      --gateway-id "${PI_GATEWAY_ID}" \
      --gateway-name "${PI_GATEWAY_NAME}" \
      --input-video-device "${PI_HDMI_RTP_DEVICE}"
  fi
fi

if [[ "${PI_HDMI_RTP_CONFIGURE_INPUT}" == "1" || "${PI_HDMI_RTP_CONFIGURE_INPUT}" == "true" || "${PI_HDMI_RTP_CONFIGURE_INPUT}" == "yes" || "${PI_HDMI_RTP_CONFIGURE_INPUT}" == "on" ]]; then
  if [[ -x "${RUNTIME_CONFIGURE_SCRIPT}" ]]; then
    bash "${RUNTIME_CONFIGURE_SCRIPT}" \
      --input-video-device "${PI_HDMI_RTP_DEVICE}" \
      --width "${PI_HDMI_RTP_WIDTH}" \
      --height "${PI_HDMI_RTP_HEIGHT}"
  elif [[ -x "${LEGACY_CONFIGURE_SCRIPT}" ]]; then
    bash "${LEGACY_CONFIGURE_SCRIPT}" \
      --input-video-device "${PI_HDMI_RTP_DEVICE}" \
      --width "${PI_HDMI_RTP_WIDTH}" \
      --height "${PI_HDMI_RTP_HEIGHT}"
  else
    echo "Pi HDMI configure script not found. Tried: ${RUNTIME_CONFIGURE_SCRIPT} ${LEGACY_CONFIGURE_SCRIPT}" >&2
    exit 1
  fi
fi

if ! pgrep -f '[s]tart_pi_hdmi_rtp_stream.sh' >/dev/null 2>&1; then
  if [[ -x "${RUNTIME_SCRIPT}" ]]; then
    nohup bash "${RUNTIME_SCRIPT}" >"${LOG_FILE}" 2>&1 < /dev/null &
  elif [[ -x "${LEGACY_SCRIPT}" ]]; then
    nohup bash "${LEGACY_SCRIPT}" >"${LOG_FILE}" 2>&1 < /dev/null &
  else
    echo "Pi RTP start script not found. Tried: ${RUNTIME_SCRIPT} ${LEGACY_SCRIPT}" >&2
    exit 1
  fi
fi

sleep 1
if pgrep -f '[s]tart_pi_hdmi_rtp_stream.sh' >/dev/null 2>&1 && \
   pgrep -f '[d]ut_result_receiver' >/dev/null 2>&1 && \
   pgrep -f '[g]ateway_agent' >/dev/null 2>&1; then
  echo "pi_gateway_stack_ready rtp_log=${LOG_FILE} agent_log=${GATEWAY_AGENT_LOG_FILE} result_receiver_log=${DUT_RESULT_RECEIVER_LOG_FILE}"
  exit 0
fi

echo "Pi gateway stack did not fully stay up. Recent logs:" >&2
tail -n 40 "${LOG_FILE}" >&2 || true
tail -n 40 "${GATEWAY_AGENT_LOG_FILE}" >&2 || true
tail -n 40 "${DUT_RESULT_RECEIVER_LOG_FILE}" >&2 || true
exit 1
EOF
