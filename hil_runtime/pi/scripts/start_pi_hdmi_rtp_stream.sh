#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"
CONFIGURE_HDMI_INPUT_BEFORE_STREAM="${PI_HDMI_RTP_CONFIGURE_INPUT:-1}"
CONFIGURE_SCRIPT="${SCRIPT_DIR}/configure_pi_hdmi_input.sh"

DEVICE="${PI_HDMI_RTP_DEVICE:-/dev/video0}"
TARGET_HOST="${PI_HDMI_RTP_TARGET_HOST:-192.168.50.2}"
TARGET_PORT="${PI_HDMI_RTP_TARGET_PORT:-5000}"
WIDTH="${PI_HDMI_RTP_WIDTH:-1920}"
HEIGHT="${PI_HDMI_RTP_HEIGHT:-1080}"
FRAMERATE="${PI_HDMI_RTP_FRAMERATE:-30}"
ENCODER="${PI_HDMI_RTP_ENCODER:-auto}"
NETWORK_INTERFACE="${PI_HDMI_RTP_NETWORK_INTERFACE:-eth0}"
INPUT_PIXFMT="${PI_HDMI_RTP_INPUT_PIXFMT:-RGB3}"
FORCE_V4L2_FORMAT="${PI_HDMI_RTP_FORCE_V4L2_FORMAT:-1}"
BITRATE_KBPS="${PI_HDMI_RTP_BITRATE_KBPS:-8000}"
CONFIG_FILE="${PI_HDMI_RTP_CONFIG_FILE:-/tmp/duckpark_pi_hdmi_rtp_config.json}"
GST_LAUNCH_BIN="${GST_LAUNCH_BIN:-gst-launch-1.0}"
GST_INSPECT_BIN="${GST_INSPECT_BIN:-gst-inspect-1.0}"

usage() {
  cat <<'EOF'
Usage:
  bash hil_runtime/pi/scripts/start_pi_hdmi_rtp_stream.sh [options]

Options:
  --device <path>         Input video node, default /dev/video0
  --host <ip>             RTP target host, default 192.168.50.2
  --port <port>           RTP target port, default 5000
  --width <pixels>        Capture width, default 1920
  --height <pixels>       Capture height, default 1080
  --framerate <fps>       Output framerate after videorate, default 30
  --encoder <name>        auto | v4l2h264enc | x264enc
  --help                  Show this help

Environment overrides:
  PI_HDMI_RTP_ENCODER_ARGS
    Optional extra encoder arguments for hardware encoder selection.
  PI_HDMI_RTP_NETWORK_INTERFACE
    Network interface used for Pi -> Jetson direct link diagnostics, default eth0.
  PI_HDMI_RTP_INPUT_PIXFMT
    V4L2 pixel format forced before launch when PI_HDMI_RTP_FORCE_V4L2_FORMAT=1, default RGB3.
  PI_HDMI_RTP_FORCE_V4L2_FORMAT
    When true, run v4l2-ctl --set-fmt-video before launch, default 1.
  PI_HDMI_RTP_BITRATE_KBPS
    Default H.264 bitrate for x264enc fallback, default 8000.
  PI_HDMI_RTP_CONFIGURE_INPUT
    When true, run configure_pi_hdmi_input.sh first so EDID/HPD and the media graph
    are refreshed before starting RTP, default 1.
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
    --device)
      require_arg_value "$@"
      DEVICE="$2"
      shift 2
      ;;
    --host)
      require_arg_value "$@"
      TARGET_HOST="$2"
      shift 2
      ;;
    --port)
      require_arg_value "$@"
      TARGET_PORT="$2"
      shift 2
      ;;
    --width)
      require_arg_value "$@"
      WIDTH="$2"
      shift 2
      ;;
    --height)
      require_arg_value "$@"
      HEIGHT="$2"
      shift 2
      ;;
    --framerate)
      require_arg_value "$@"
      FRAMERATE="$2"
      shift 2
      ;;
    --encoder)
      require_arg_value "$@"
      ENCODER="$2"
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
  printf '%s pi-hdmi-rtp %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

bool_flag() {
  local value
  value=$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')
  [[ "${value}" == "1" || "${value}" == "true" || "${value}" == "yes" || "${value}" == "on" ]]
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

have_gst_element() {
  "${GST_INSPECT_BIN}" "$1" >/dev/null 2>&1
}

split_words_to_array() {
  local -n target_ref=$1
  local raw_value="$2"
  local word
  target_ref=()
  # shellcheck disable=SC2206
  local expanded=( ${raw_value} )
  for word in "${expanded[@]}"; do
    target_ref+=("${word}")
  done
}

select_encoder() {
  if [[ "${ENCODER}" != "auto" ]]; then
    printf '%s\n' "${ENCODER}"
    return 0
  fi

  if have_gst_element "v4l2h264enc"; then
    printf '%s\n' "v4l2h264enc"
    return 0
  fi

  if have_gst_element "x264enc"; then
    printf '%s\n' "x264enc"
    return 0
  fi

  echo "No supported H264 encoder found (expected v4l2h264enc or x264enc)" >&2
  exit 1
}

build_encoder_args() {
  local selected_encoder="$1"
  local inspect_output=""
  local -a args=()
  local arg

  if [[ -n "${PI_HDMI_RTP_ENCODER_ARGS:-}" ]]; then
    split_words_to_array args "${PI_HDMI_RTP_ENCODER_ARGS}"
    for arg in "${args[@]}"; do
      printf '%s\0' "${arg}"
    done
    return 0
  fi

  inspect_output="$("${GST_INSPECT_BIN}" "${selected_encoder}" 2>/dev/null || true)"

  case "${selected_encoder}" in
    v4l2h264enc)
      if grep -q "extra-controls" <<<"${inspect_output}"; then
        args=(
          "extra-controls=controls,repeat_sequence_header=1,video_b_frames=0,h264_i_frame_period=1"
        )
      elif grep -q "iframeinterval" <<<"${inspect_output}"; then
        args=("iframeinterval=1")
        if grep -Eq '(^|[[:space:]])bframes($|[[:space:]])' <<<"${inspect_output}"; then
          args+=("bframes=0")
        fi
        if grep -Eq 'repeat[-_]sequence[-_]header' <<<"${inspect_output}"; then
          args+=("repeat-sequence-header=true")
        fi
      fi
      ;;
    x264enc)
      args=(
        "tune=zerolatency"
        "speed-preset=ultrafast"
        "bitrate=${BITRATE_KBPS}"
        "key-int-max=${FRAMERATE}"
        "bframes=0"
        "cabac=false"
        "byte-stream=true"
      )
      ;;
  esac

  for arg in "${args[@]}"; do
    printf '%s\0' "${arg}"
  done
}

if [[ ! -e "${DEVICE}" ]]; then
  echo "Video device does not exist: ${DEVICE}" >&2
  exit 1
fi

require_command "${GST_LAUNCH_BIN}"
require_command "${GST_INSPECT_BIN}"

if bool_flag "${CONFIGURE_HDMI_INPUT_BEFORE_STREAM}"; then
  if [[ ! -x "${CONFIGURE_SCRIPT}" ]]; then
    echo "HDMI configure script not found: ${CONFIGURE_SCRIPT}" >&2
    exit 1
  fi
  log "refreshing HDMI input via ${CONFIGURE_SCRIPT} so EDID/HPD and timings are ready"
  bash "${CONFIGURE_SCRIPT}" \
    --input-video-device "${DEVICE}" \
    --width "${WIDTH}" \
    --height "${HEIGHT}"
fi

SELECTED_ENCODER="$(select_encoder)"
declare -a ENCODER_ARGS=()
while IFS= read -r -d '' arg; do
  ENCODER_ARGS+=("${arg}")
done < <(build_encoder_args "${SELECTED_ENCODER}")

log "project_root=${PROJECT_ROOT}"
log "device=${DEVICE} target=${TARGET_HOST}:${TARGET_PORT} size=${WIDTH}x${HEIGHT}@${FRAMERATE}"
log "selected_encoder=${SELECTED_ENCODER}"

mkdir -p "$(dirname "${CONFIG_FILE}")"
PI_HDMI_RTP_CONFIG_FILE="${CONFIG_FILE}" \
PI_HDMI_RTP_DEVICE="${DEVICE}" \
PI_HDMI_RTP_TARGET_HOST="${TARGET_HOST}" \
PI_HDMI_RTP_TARGET_PORT="${TARGET_PORT}" \
PI_HDMI_RTP_WIDTH="${WIDTH}" \
PI_HDMI_RTP_HEIGHT="${HEIGHT}" \
PI_HDMI_RTP_FRAMERATE="${FRAMERATE}" \
PI_HDMI_RTP_ENCODER="${SELECTED_ENCODER}" \
PI_HDMI_RTP_NETWORK_INTERFACE="${NETWORK_INTERFACE}" \
PI_HDMI_RTP_INPUT_PIXFMT="${INPUT_PIXFMT}" \
PI_HDMI_RTP_FORCE_V4L2_FORMAT="${FORCE_V4L2_FORMAT}" \
PI_HDMI_RTP_BITRATE_KBPS="${BITRATE_KBPS}" \
DUCKPARK_PLATFORM_ROOT="${PROJECT_ROOT}" \
python3 - <<'PY'
import json
import os
import socket
import time
from pathlib import Path

payload = {
    "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "hostname": socket.gethostname(),
    "project_root": os.environ.get("DUCKPARK_PLATFORM_ROOT", ""),
    "device": os.environ.get("PI_HDMI_RTP_DEVICE", ""),
    "target_host": os.environ.get("PI_HDMI_RTP_TARGET_HOST", ""),
    "target_port": os.environ.get("PI_HDMI_RTP_TARGET_PORT", ""),
    "width": os.environ.get("PI_HDMI_RTP_WIDTH", ""),
    "height": os.environ.get("PI_HDMI_RTP_HEIGHT", ""),
    "framerate": os.environ.get("PI_HDMI_RTP_FRAMERATE", ""),
    "encoder": os.environ.get("PI_HDMI_RTP_ENCODER", ""),
    "network_interface": os.environ.get("PI_HDMI_RTP_NETWORK_INTERFACE", ""),
    "input_pixfmt": os.environ.get("PI_HDMI_RTP_INPUT_PIXFMT", ""),
    "force_v4l2_format": os.environ.get("PI_HDMI_RTP_FORCE_V4L2_FORMAT", ""),
    "bitrate_kbps": os.environ.get("PI_HDMI_RTP_BITRATE_KBPS", ""),
}
Path(os.environ["PI_HDMI_RTP_CONFIG_FILE"]).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY
log "config_dump=${CONFIG_FILE}"

if command -v v4l2-ctl >/dev/null 2>&1; then
  if bool_flag "${FORCE_V4L2_FORMAT}"; then
    log "forcing v4l2 capture format width=${WIDTH} height=${HEIGHT} pixelformat=${INPUT_PIXFMT}"
    v4l2-ctl -d "${DEVICE}" \
      --set-fmt-video="width=${WIDTH},height=${HEIGHT},pixelformat=${INPUT_PIXFMT}"
  fi
  log "capturing v4l2 diagnostics"
  v4l2-ctl -d "${DEVICE}" --get-fmt-video 2>/dev/null | sed 's/^/  /' || true
  v4l2-ctl -d "${DEVICE}" --all 2>/dev/null | sed 's/^/  /' || true
fi

if ip -4 addr show "${NETWORK_INTERFACE}" >/dev/null 2>&1; then
  log "${NETWORK_INTERFACE} IPv4 configuration"
  ip -4 addr show "${NETWORK_INTERFACE}" | sed 's/^/  /'
else
  log "${NETWORK_INTERFACE} interface not present on Pi at launch time"
fi

PIPELINE=(
  "${GST_LAUNCH_BIN}"
  -e
  v4l2src
  "device=${DEVICE}"
  "do-timestamp=true"
  !
  "video/x-raw,format=RGB,width=${WIDTH},height=${HEIGHT}"
  !
  queue
  "max-size-buffers=4"
  "leaky=downstream"
  !
  videoconvert
  !
  videorate
  !
  "video/x-raw,format=I420,width=${WIDTH},height=${HEIGHT},framerate=${FRAMERATE}/1"
  !
  "${SELECTED_ENCODER}"
)
PIPELINE+=("${ENCODER_ARGS[@]}")
PIPELINE+=(
  !
  h264parse
  !
  rtph264pay
  "config-interval=1"
  "pt=96"
  !
  udpsink
  "host=${TARGET_HOST}"
  "port=${TARGET_PORT}"
  "sync=false"
  "async=false"
)

log "starting GStreamer RTP pipeline"
printf '  %q' "${PIPELINE[@]}"
printf '\n'

PIPELINE_PID=""
cleanup() {
  local exit_code=$?
  if [[ -n "${PIPELINE_PID}" ]] && kill -0 "${PIPELINE_PID}" >/dev/null 2>&1; then
    log "stopping RTP pipeline pid=${PIPELINE_PID}"
    kill -INT "${PIPELINE_PID}" >/dev/null 2>&1 || true
    wait "${PIPELINE_PID}" 2>/dev/null || true
  fi
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

"${PIPELINE[@]}" &
PIPELINE_PID=$!
wait "${PIPELINE_PID}"
