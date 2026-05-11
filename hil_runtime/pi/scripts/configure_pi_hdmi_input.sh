#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"
STATE_DIR="${PI_GATEWAY_STATE_DIR:-${PROJECT_ROOT}/run_data/pi_gateway}"
STATE_FILE="${STATE_DIR}/bridge_state.json"

MEDIA_DEVICE="${PI_GATEWAY_MEDIA_DEVICE:-}"
HDMI_STATUS_DEVICE="${PI_GATEWAY_HDMI_STATUS_DEVICE:-/dev/v4l-subdev2}"
INPUT_VIDEO_DEVICE="${PI_GATEWAY_INPUT_VIDEO_DEVICE:-/dev/video0}"
EDID_TYPE="${PI_GATEWAY_HDMI_EDID_TYPE:-hdmi}"
WIDTH=""
HEIGHT=""

usage() {
  cat <<'EOF'
用法:
  bash hil_runtime/pi/scripts/configure_pi_hdmi_input.sh [options]

可选参数:
  --media-device <path>         media device，默认自动探测 rp1-cfe
  --hdmi-status-device <path>   tc358743 subdev，默认 /dev/v4l-subdev2
  --input-video-device <path>   采集节点，默认 /dev/video0
  --edid-type <type>            默认 hdmi
  --width <pixels>              手动指定宽度
  --height <pixels>             手动指定高度
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
    --edid-type)
      require_arg_value "$@"
      EDID_TYPE="$2"
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

if [[ ! -e "${MEDIA_DEVICE}" || ! -e "${HDMI_STATUS_DEVICE}" || ! -e "${INPUT_VIDEO_DEVICE}" ]]; then
  echo "缺少 HDMI 输入相关设备节点" >&2
  exit 1
fi

v4l2-ctl -d "${HDMI_STATUS_DEVICE}" --set-edid "pad=0,type=${EDID_TYPE}"
sleep 1

# tc358743 在热插拔后可能只更新 detected timings，未同步到 current timings。
# 主动执行一次 query sync，避免后续 capture node 卡死在错误时序上。
v4l2-ctl -d "${HDMI_STATUS_DEVICE}" --set-dv-bt-timings query >/dev/null 2>&1 || true

STATUS_LOG=$(v4l2-ctl -d "${HDMI_STATUS_DEVICE}" --log-status 2>&1 || true)
if [[ -z "${WIDTH}" || -z "${HEIGHT}" ]]; then
  RESOLUTION=$(printf '%s\n' "${STATUS_LOG}" | sed -n 's/.*Detected format: \([0-9]\+\)x\([0-9]\+\).*/\1 \2/p' | head -n1)
  if [[ -z "${RESOLUTION}" ]]; then
    RESOLUTION=$(printf '%s\n' "${STATUS_LOG}" | sed -n 's/.*Configured format: \([0-9]\+\)x\([0-9]\+\).*/\1 \2/p' | head -n1)
  fi
  if [[ -n "${RESOLUTION}" ]]; then
    WIDTH="${WIDTH:-$(printf '%s' "${RESOLUTION}" | awk '{print $1}')}"
    HEIGHT="${HEIGHT:-$(printf '%s' "${RESOLUTION}" | awk '{print $2}')}"
  fi
fi

WIDTH="${WIDTH:-640}"
HEIGHT="${HEIGHT:-480}"

TMDS_STATUS=$(printf '%s\n' "${STATUS_LOG}" | sed -n 's/.*TMDS signal detected: \(yes\|no\).*/\1/p' | head -n1)
SYNC_STATUS=$(printf '%s\n' "${STATUS_LOG}" | sed -n 's/.*Stable sync signal: \(yes\|no\).*/\1/p' | head -n1)
HOTPLUG_STATUS=$(printf '%s\n' "${STATUS_LOG}" | sed -n 's/.*Hotplug enabled: \(yes\|no\).*/\1/p' | head -n1)
export HOTPLUG_STATUS TMDS_STATUS SYNC_STATUS

media-ctl -d "${MEDIA_DEVICE}" -V "\"tc358743 11-000f\":0 [fmt:RGB888_1X24/${WIDTH}x${HEIGHT} field:none colorspace:srgb]"
media-ctl -d "${MEDIA_DEVICE}" -V "\"csi2\":0 [fmt:RGB888_1X24/${WIDTH}x${HEIGHT} field:none colorspace:srgb]"
media-ctl -d "${MEDIA_DEVICE}" -V "\"csi2\":4 [fmt:RGB888_1X24/${WIDTH}x${HEIGHT} field:none colorspace:srgb]"
media-ctl -d "${MEDIA_DEVICE}" -l "\"csi2\":4 -> \"rp1-cfe-csi2_ch0\":0 [1]"
v4l2-ctl -d "${INPUT_VIDEO_DEVICE}" --set-fmt-video="width=${WIDTH},height=${HEIGHT},pixelformat=RGB3" >/dev/null

python3 - <<PY
import json
import os
from pathlib import Path

state_path = Path("${STATE_FILE}")

def parse_bool(name: str):
    raw = os.environ.get(name, "")
    if raw == "yes":
        return True
    if raw == "no":
        return False
    return None

payload = {
    "configured_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "bridge_mode": "hdmi_to_uvc",
    "media_device": "${MEDIA_DEVICE}",
    "hdmi_status_device": "${HDMI_STATUS_DEVICE}",
    "input_video_device": "${INPUT_VIDEO_DEVICE}",
    "capture_width": int("${WIDTH}"),
    "capture_height": int("${HEIGHT}"),
    "capture_pixel_format": "RGB3",
    "hdmi_edid_type": "${EDID_TYPE}",
    "dv_timings_synced": True,
    "hdmi_hotplug_enabled": parse_bool("HOTPLUG_STATUS"),
    "hdmi_tmds_signal_detected": parse_bool("TMDS_STATUS"),
    "hdmi_stable_sync_signal": parse_bool("SYNC_STATUS"),
    "capture_link_enabled": True,
}
state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
PY

if [[ "${TMDS_STATUS}" != "yes" || "${SYNC_STATUS}" != "yes" ]]; then
  cat >&2 <<EOF
HDMI 输入未激活，已完成 EDID/HPD 与 media pipeline 配置，但当前仍未检测到稳定视频。

当前状态:
  Hotplug enabled: ${HOTPLUG_STATUS:-unknown}
  TMDS signal detected: ${TMDS_STATUS:-unknown}
  Stable sync signal: ${SYNC_STATUS:-unknown}

请检查 HDMI 源设备是否正在输出，并重新插拔 HDMI 线或刷新源端显示输出。

如果 HDMI 源来自 Ubuntu 主机，请额外确认 HDMI 输出口不是只有“connected”，而是真的被激活成镜像显示。
一个常用修复命令是：

  DISPLAY=:1 XAUTHORITY=/home/du/.Xauthority \
  xrandr --output HDMI-0 --mode 1920x1080 --rate 60 --same-as DP-0

然后再重新执行当前脚本，或重新触发 Pi RTP 启动链路。
EOF
  exit 2
fi

echo "HDMI input configured: ${INPUT_VIDEO_DEVICE} ${WIDTH}x${HEIGHT} RGB3"
