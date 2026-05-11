#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"
STATE_DIR="${PI_GATEWAY_STATE_DIR:-${PROJECT_ROOT}/run_data/pi_gateway}"
BRIDGE_STATE_FILE="${STATE_DIR}/bridge_state.json"

MEDIA_DEVICE="${PI_GATEWAY_MEDIA_DEVICE:-}"
HDMI_STATUS_DEVICE="${PI_GATEWAY_HDMI_STATUS_DEVICE:-/dev/v4l-subdev2}"
INPUT_VIDEO_DEVICE="${PI_GATEWAY_INPUT_VIDEO_DEVICE:-/dev/video0}"
SAVE_DIR=""
SAVE_FORMAT="jpg"
SAMPLE_FPS="2"
MAX_FRAMES="300"

usage() {
  cat <<'EOF'
用法:
  bash hil_runtime/pi/scripts/start_pi_frame_capture.sh [options]

必选参数:
  --save-dir <path>             保存目录

可选参数:
  --save-format <jpg|png>       保存格式，默认 jpg
  --sample-fps <fps>            采样帧率，默认 2
  --max-frames <count>          最大帧数，默认 300
  --media-device <path>         media device，默认自动探测 rp1-cfe
  --hdmi-status-device <path>   tc358743 subdev，默认 /dev/v4l-subdev2
  --input-video-device <path>   采集节点，默认 /dev/video0
  --help                        输出帮助
EOF
}

require_arg_value() {
  if [[ $# -lt 2 || -z "${2:-}" ]]; then
    echo "参数 $1 缺少取值" >&2
    usage >&2
    exit 1
  fi
}

while (($# > 0)); do
  case "$1" in
    --save-dir)
      require_arg_value "$@"
      SAVE_DIR="$2"
      shift 2
      ;;
    --save-format)
      require_arg_value "$@"
      SAVE_FORMAT="$2"
      shift 2
      ;;
    --sample-fps)
      require_arg_value "$@"
      SAMPLE_FPS="$2"
      shift 2
      ;;
    --max-frames)
      require_arg_value "$@"
      MAX_FRAMES="$2"
      shift 2
      ;;
    --media-device)
      require_arg_value "$@"
      MEDIA_DEVICE="$2"
      shift 2
      ;;
    --hdmi-status-device)
      require_arg_value "$@"
      HDMI_STATUS_DEVICE="$2"
      shift 2
      ;;
    --input-video-device)
      require_arg_value "$@"
      INPUT_VIDEO_DEVICE="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${SAVE_DIR}" ]]; then
  echo "--save-dir 为必填参数" >&2
  usage >&2
  exit 1
fi

SAVE_FORMAT="$(printf '%s' "${SAVE_FORMAT}" | tr '[:upper:]' '[:lower:]')"
if [[ "${SAVE_FORMAT}" != "jpg" && "${SAVE_FORMAT}" != "png" ]]; then
  echo "当前仅支持 jpg 或 png 保存格式" >&2
  exit 2
fi

CONFIG_ARGS=(
  --hdmi-status-device "${HDMI_STATUS_DEVICE}"
  --input-video-device "${INPUT_VIDEO_DEVICE}"
)
if [[ -n "${MEDIA_DEVICE}" ]]; then
  CONFIG_ARGS+=(--media-device "${MEDIA_DEVICE}")
fi

bash "${SCRIPT_DIR}/configure_pi_hdmi_input.sh" "${CONFIG_ARGS[@]}"

WIDTH="$(python3 - <<PY
import json
from pathlib import Path
payload = json.loads(Path("${BRIDGE_STATE_FILE}").read_text(encoding="utf-8"))
print(payload["capture_width"])
PY
)"
HEIGHT="$(python3 - <<PY
import json
from pathlib import Path
payload = json.loads(Path("${BRIDGE_STATE_FILE}").read_text(encoding="utf-8"))
print(payload["capture_height"])
PY
)"

mkdir -p "${SAVE_DIR}/frames"
OUTPUT_PATTERN="${SAVE_DIR}/frames/frame_%06d.${SAVE_FORMAT}"

FFMPEG_ARGS=(
  -hide_banner
  -loglevel warning
  -nostdin
  -y
  -fflags nobuffer
  -f v4l2
  -input_format rgb24
  -framerate 30
  -video_size "${WIDTH}x${HEIGHT}"
  -i "${INPUT_VIDEO_DEVICE}"
  -vf "fps=${SAMPLE_FPS}"
  -frames:v "${MAX_FRAMES}"
)

if [[ "${SAVE_FORMAT}" == "jpg" ]]; then
  FFMPEG_ARGS+=(-q:v 2)
fi

exec ffmpeg "${FFMPEG_ARGS[@]}" "${OUTPUT_PATTERN}"
