#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"
source "${SCRIPT_DIR}/pi_gadget_common.sh"

STATE_DIR="${PI_GATEWAY_STATE_DIR:-${PROJECT_ROOT}/run_data/pi_gateway}"
STATE_FILE="${STATE_DIR}/bridge_state.json"

MEDIA_DEVICE="${PI_GATEWAY_MEDIA_DEVICE:-}"
HDMI_STATUS_DEVICE="${PI_GATEWAY_HDMI_STATUS_DEVICE:-/dev/v4l-subdev2}"
INPUT_VIDEO_DEVICE="${PI_GATEWAY_INPUT_VIDEO_DEVICE:-/dev/video0}"
FRAMERATE="${PI_GATEWAY_BRIDGE_FRAMERATE:-30}"
WIDTH=""
HEIGHT=""
GADGET_OUTPUT_WIDTH=""
GADGET_OUTPUT_HEIGHT=""
GADGET_OUTPUT_FPS=""

usage() {
  cat <<'EOF'
用法:
  bash hil_runtime/pi/scripts/start_pi_hdmi_to_uvc_bridge.sh [options]

可选参数:
  --media-device <path>         media device，默认自动探测 rp1-cfe
  --hdmi-status-device <path>   tc358743 subdev，默认 /dev/v4l-subdev2
  --input-video-device <path>   采集节点，默认 /dev/video0
  --width <pixels>              手动指定宽度
  --height <pixels>             手动指定高度
  --framerate <fps>             输出帧率，默认 30
  --gadget-width <pixels>       强制指定 UVC 输出宽度
  --gadget-height <pixels>      强制指定 UVC 输出高度
  --gadget-fps <fps>            强制指定 UVC 输出帧率
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

find_rp1_cfe_media_device() {
  local dev
  for dev in /dev/media*; do
    [[ -e "${dev}" ]] || continue
    if media-ctl -d "${dev}" -p 2>/dev/null | grep -qE '^(driver|model)[[:space:]]+rp1-cfe$'; then
      printf '%s\n' "${dev}"
      return 0
    fi
  done
  return 1
}

get_udc_state() {
  local udc_name
  udc_name="$(ls /sys/class/udc 2>/dev/null | head -n1 || true)"
  if [[ -z "${udc_name}" ]]; then
    return 1
  fi
  cat "/sys/class/udc/${udc_name}/state" 2>/dev/null || true
}

select_gadget_output_profile() {
  python3 - "${GADGET_VIDEO_DEVICE}" "${WIDTH}" "${HEIGHT}" "${FRAMERATE}" <<'PY'
import re
import subprocess
import sys

device, source_width, source_height, desired_fps = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
output = subprocess.run(
    ["v4l2-ctl", "-d", device, "--list-formats-out-ext"],
    capture_output=True,
    check=False,
    text=True,
    timeout=3.0,
).stdout

current_pixfmt = None
current_width = None
current_height = None
modes = []

for raw_line in output.splitlines():
    line = raw_line.strip()
    pixfmt_match = re.match(r"\[\d+\]: '([^']+)'", line)
    if pixfmt_match:
        current_pixfmt = pixfmt_match.group(1)
        current_width = None
        current_height = None
        continue

    size_match = re.match(r"Size:\s+Discrete\s+(\d+)x(\d+)", line)
    if size_match:
        current_width = int(size_match.group(1))
        current_height = int(size_match.group(2))
        continue

    interval_match = re.match(r"Interval:\s+Discrete\s+[0-9.]+s\s+\(([0-9.]+)\s+fps\)", line)
    if interval_match and current_pixfmt == "YUYV" and current_width and current_height:
        modes.append(
            {
                "pixfmt": current_pixfmt,
                "width": current_width,
                "height": current_height,
                "fps": float(interval_match.group(1)),
            }
        )

if not modes:
    raise SystemExit(1)

modes = [mode for mode in modes if mode["width"] <= source_width and mode["height"] <= source_height]
if not modes:
    raise SystemExit(1)

at_least_desired = [mode for mode in modes if mode["fps"] >= desired_fps]
if at_least_desired:
    chosen = sorted(
        at_least_desired,
        key=lambda mode: (
            -(mode["width"] * mode["height"]),
            abs(mode["fps"] - desired_fps),
            -mode["fps"],
        ),
    )[0]
else:
    chosen = sorted(
        modes,
        key=lambda mode: (-mode["fps"], -(mode["width"] * mode["height"])),
    )[0]

print(chosen["width"], chosen["height"], f"{chosen['fps']:.3f}")
PY
}

while (($# > 0)); do
  case "$1" in
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
    --gadget-width)
      require_arg_value "$@"
      GADGET_OUTPUT_WIDTH="$2"
      shift 2
      ;;
    --gadget-height)
      require_arg_value "$@"
      GADGET_OUTPUT_HEIGHT="$2"
      shift 2
      ;;
    --gadget-fps)
      require_arg_value "$@"
      GADGET_OUTPUT_FPS="$2"
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

if [[ -z "${MEDIA_DEVICE}" ]]; then
  MEDIA_DEVICE="$(find_rp1_cfe_media_device || true)"
fi

if [[ -z "${MEDIA_DEVICE}" ]]; then
  echo "未找到 rp1-cfe media device，请手动传入 --media-device" >&2
  exit 1
fi

mkdir -p "${STATE_DIR}"

bash "${SCRIPT_DIR}/start_pi_uvc_gadget.sh"
CONFIG_ARGS=(
  --media-device "${MEDIA_DEVICE}"
  --hdmi-status-device "${HDMI_STATUS_DEVICE}"
  --input-video-device "${INPUT_VIDEO_DEVICE}"
)
if [[ -n "${WIDTH}" ]]; then
  CONFIG_ARGS+=(--width "${WIDTH}")
fi
if [[ -n "${HEIGHT}" ]]; then
  CONFIG_ARGS+=(--height "${HEIGHT}")
fi

bash "${SCRIPT_DIR}/configure_pi_hdmi_input.sh" "${CONFIG_ARGS[@]}"

GADGET_VIDEO_DEVICE="$(find_gadget_video_device || true)"
if [[ -z "${GADGET_VIDEO_DEVICE}" ]]; then
  echo "未找到 UVC gadget 输出节点" >&2
  exit 1
fi

UDC_STATE="$(get_udc_state || true)"
if [[ "${UDC_STATE}" == "not attached" || -z "${UDC_STATE}" ]]; then
  cat >&2 <<EOF
UVC gadget 尚未连接到 USB host。

当前状态:
  gadget_video_device: ${GADGET_VIDEO_DEVICE}
  udc_state: ${UDC_STATE:-missing}

请先将树莓派 USB-C OTG 口连接到 DUT 或测试主机，待 UDC state 变为 configured 后再启动 HDMI->UVC bridge。
EOF
  exit 2
fi

if [[ -f "${STATE_FILE}" ]]; then
  WIDTH="$(python3 - <<PY
import json
from pathlib import Path
payload = json.loads(Path("${STATE_FILE}").read_text(encoding="utf-8"))
print(payload.get("capture_width", ${WIDTH:-640}))
PY
)"
  HEIGHT="$(python3 - <<PY
import json
from pathlib import Path
payload = json.loads(Path("${STATE_FILE}").read_text(encoding="utf-8"))
print(payload.get("capture_height", ${HEIGHT:-480}))
PY
)"
fi

if [[ -z "${GADGET_OUTPUT_WIDTH}" || -z "${GADGET_OUTPUT_HEIGHT}" || -z "${GADGET_OUTPUT_FPS}" ]]; then
  GADGET_PROFILE="$(select_gadget_output_profile || true)"
  if [[ -z "${GADGET_PROFILE}" ]]; then
    echo "无法从 ${GADGET_VIDEO_DEVICE} 探测到可用的 YUYV 输出模式" >&2
    exit 1
  fi
  read -r GADGET_OUTPUT_WIDTH GADGET_OUTPUT_HEIGHT GADGET_OUTPUT_FPS <<<"${GADGET_PROFILE}"
fi

v4l2-ctl \
  -d "${GADGET_VIDEO_DEVICE}" \
  --set-fmt-video-out="width=${GADGET_OUTPUT_WIDTH},height=${GADGET_OUTPUT_HEIGHT},pixelformat=YUYV" \
  >/dev/null

python3 - <<PY
import json
from pathlib import Path

state_path = Path("${STATE_FILE}")
payload = json.loads(state_path.read_text(encoding="utf-8"))
payload.update(
    {
        "bridge_running": True,
        "bridge_started_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "bridge_framerate": int("${FRAMERATE}"),
        "gadget_video_device": "${GADGET_VIDEO_DEVICE}",
        "gadget_pixel_format": "YUYV",
        "gadget_output_width": int("${GADGET_OUTPUT_WIDTH}"),
        "gadget_output_height": int("${GADGET_OUTPUT_HEIGHT}"),
        "gadget_output_fps": float("${GADGET_OUTPUT_FPS}"),
        "udc_state": "${UDC_STATE}",
    }
)
state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
PY

exec ffmpeg \
  -hide_banner \
  -loglevel warning \
  -fflags nobuffer \
  -f v4l2 \
  -input_format rgb24 \
  -framerate "${FRAMERATE}" \
  -video_size "${WIDTH}x${HEIGHT}" \
  -i "${INPUT_VIDEO_DEVICE}" \
  -vf "fps=${GADGET_OUTPUT_FPS},scale=${GADGET_OUTPUT_WIDTH}:${GADGET_OUTPUT_HEIGHT}" \
  -pix_fmt yuyv422 \
  -f v4l2 \
  "${GADGET_VIDEO_DEVICE}"
