#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"

PLATFORM_HOST=""
PLATFORM_PORT="8000"
GATEWAY_ID=""
GATEWAY_NAME=""
INPUT_VIDEO_DEVICE="${PI_GATEWAY_INPUT_VIDEO_DEVICE:-/dev/video0}"
HEARTBEAT_INTERVAL="${PI_GATEWAY_HEARTBEAT_INTERVAL_SECONDS:-5}"
ONCE="false"

usage() {
  cat <<'EOF'
用法:
  bash hil_runtime/pi/scripts/start_pi_gateway_stack.sh \
    --platform-host 192.168.110.151 \
    --platform-port 8000 \
    --gateway-id rpi5-x1301-01 \
    --gateway-name bench-a

可选参数:
  --platform-host <host>          平台 API 主机地址
  --platform-port <port>          平台 API 端口，默认 8000
  --gateway-id <id>               网关 ID
  --gateway-name <name>           网关名称
  --input-video-device <path>     输入视频节点，默认 /dev/video0
  --heartbeat-interval <seconds>  心跳周期，默认 5 秒
  --once                          仅注册并发送一次心跳
  --help                          输出帮助
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
    --platform-host)
      require_arg_value "$@"
      PLATFORM_HOST="$2"
      shift 2
      ;;
    --platform-port)
      require_arg_value "$@"
      PLATFORM_PORT="$2"
      shift 2
      ;;
    --gateway-id)
      require_arg_value "$@"
      GATEWAY_ID="$2"
      shift 2
      ;;
    --gateway-name)
      require_arg_value "$@"
      GATEWAY_NAME="$2"
      shift 2
      ;;
    --input-video-device)
      require_arg_value "$@"
      INPUT_VIDEO_DEVICE="$2"
      shift 2
      ;;
    --heartbeat-interval)
      require_arg_value "$@"
      HEARTBEAT_INTERVAL="$2"
      shift 2
      ;;
    --once)
      ONCE="true"
      shift
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

if [[ -z "${PLATFORM_HOST}" || -z "${GATEWAY_ID}" || -z "${GATEWAY_NAME}" ]]; then
  usage >&2
  exit 1
fi

bash "${SCRIPT_DIR}/start_pi_uvc_gadget.sh"

AGENT_ARGS=(
  --api-base-url "http://${PLATFORM_HOST}:${PLATFORM_PORT}"
  --gateway-id "${GATEWAY_ID}"
  --gateway-name "${GATEWAY_NAME}"
  --input-video-device "${INPUT_VIDEO_DEVICE}"
  --heartbeat-interval "${HEARTBEAT_INTERVAL}"
)

if [[ "${ONCE}" == "true" ]]; then
  AGENT_ARGS+=(--once)
fi

exec bash "${SCRIPT_DIR}/start_pi_gateway_agent.sh" "${AGENT_ARGS[@]}"
