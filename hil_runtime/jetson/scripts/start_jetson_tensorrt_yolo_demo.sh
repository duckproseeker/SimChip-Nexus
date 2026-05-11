#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"
TIME_SYNC_ENABLED="${JETSON_SYNC_TIME_FROM_PI:-1}"

WORKSPACE_DIR="${JETSON_WORKSPACE_DIR:-$HOME/yolo_ros2}"
WORKSPACE_SETUP="${JETSON_WORKSPACE_SETUP:-${WORKSPACE_DIR}/install/setup.bash}"
INPUT_TOPIC="${JETSON_INPUT_TOPIC:-/image_raw}"
OUTPUT_TOPIC="${JETSON_OUTPUT_TOPIC:-/duckpark/rois}"
DATA_PATH="${JETSON_YOLO_DATA_PATH:-${WORKSPACE_DIR}/module}"
MODE="${JETSON_YOLO_MODE:-FP32}"
GPU_ID="${JETSON_GPU_ID:-0}"
RESULT_URL="${JETSON_RESULT_URL:-}"
RESULT_FILE="${JETSON_RESULT_FILE:-$HOME/duckpark_yolo_result.json}"
CAMERA_DEVICE="${JETSON_CAMERA_DEVICE:-}"
SOURCE_HOST="${JETSON_SOURCE_HOST:-$(hostname)}"
RUN_ID="${JETSON_RUN_ID:-}"
CAMERA_COMMAND="${JETSON_CAMERA_COMMAND:-}"
TEGRASTATS_COMMAND="${JETSON_TEGRASTATS_COMMAND:-tegrastats --interval 1000}"
RESULT_TIMEOUT_SECONDS="${JETSON_RESULT_TIMEOUT_SECONDS:-2}"
RESULT_MAX_RETRIES="${JETSON_RESULT_MAX_RETRIES:-3}"
RESULT_RETRY_BACKOFF_SECONDS="${JETSON_RESULT_RETRY_BACKOFF_SECONDS:-1}"
SPIN_TIMEOUT_SECONDS="${JETSON_METRICS_SPIN_TIMEOUT_SECONDS:-0.1}"

detect_ros_setup() {
  local candidate
  for candidate in \
    "${JETSON_ROS_SETUP:-}" \
    /opt/ros/galactic/setup.bash \
    /opt/ros/humble/setup.bash \
    /opt/ros/foxy/setup.bash
  do
    if [[ -n "${candidate}" && -f "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

ROS_SETUP="$(detect_ros_setup || true)"

detect_yolo_type() {
  local requested_type="${JETSON_YOLO_TYPE:-}"
  local candidate
  local -a candidates=(
    "${requested_type}"
    "yolov5s"
    "yolov4-tiny"
    "yolov5m"
    "yolov5l"
    "yolov5x"
    "yolov4"
    "yolov3"
  )

  for candidate in "${candidates[@]}"; do
    if [[ -z "${candidate}" ]]; then
      continue
    fi
    if [[ -f "${DATA_PATH}/${candidate}.engine" ]] || [[ -f "${DATA_PATH}/${candidate}.onnx" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  printf '%s\n' "${requested_type:-yolov5s}"
}

YOLO_TYPE="$(detect_yolo_type)"

safe_source_setup() {
  local setup_path="$1"
  local had_nounset=0
  if [[ ! -f "${setup_path}" ]]; then
    return 1
  fi

  case $- in
    *u*) had_nounset=1 ;;
  esac

  if [[ "${had_nounset}" == "1" ]]; then
    set +u
  fi
  # shellcheck source=/dev/null
  source "${setup_path}"
  if [[ "${had_nounset}" == "1" ]]; then
    set -u
  fi
}

usage() {
  cat <<'EOF'
用法:
  JETSON_CAMERA_COMMAND='ros2 run ...' \
  JETSON_RESULT_URL='http://192.168.50.1:18765/dut-results' \
  bash hil_runtime/jetson/scripts/start_jetson_tensorrt_yolo_demo.sh

说明:
  - 该脚本不会替你猜测具体摄像头发布节点，建议通过 JETSON_CAMERA_COMMAND 传入。
  - 当前默认启动现有 tensorrt_yolo launch，并同时起一个 metrics 监控进程。
  - metrics 监控会在运行中异步上报结果，并在结束时发送最终汇总到 Pi。
  - ROS setup 默认按 galactic -> humble -> foxy 顺序自动探测。
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "${TIME_SYNC_ENABLED,,}" == "1" || "${TIME_SYNC_ENABLED,,}" == "true" || "${TIME_SYNC_ENABLED,,}" == "yes" || "${TIME_SYNC_ENABLED,,}" == "on" ]]; then
  bash "${SCRIPT_DIR}/sync_jetson_time_from_pi.sh"
fi

if [[ ! -f "${ROS_SETUP}" ]]; then
  echo "缺少 ROS setup: ${ROS_SETUP}" >&2
  exit 1
fi

if [[ ! -d "${WORKSPACE_DIR}" ]]; then
  echo "缺少工作区目录: ${WORKSPACE_DIR}" >&2
  exit 1
fi

export PROJECT_ROOT
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

safe_source_setup "${ROS_SETUP}"
if [[ -f "${WORKSPACE_SETUP}" ]]; then
  safe_source_setup "${WORKSPACE_SETUP}"
fi

if ! command -v ros2 >/dev/null 2>&1; then
  echo "ros2 command 不可用，请检查 ROS setup: ${ROS_SETUP}" >&2
  exit 1
fi

if ! ros2 pkg prefix tensorrt_yolo >/dev/null 2>&1; then
  echo "未找到 tensorrt_yolo 包，请检查工作区 overlay: ${WORKSPACE_SETUP}" >&2
  exit 1
fi

CAMERA_PID=""
METRICS_PID=""
YOLO_PID=""

cleanup() {
  local exit_code=$?
  if [[ -n "${YOLO_PID}" ]] && kill -0 "${YOLO_PID}" >/dev/null 2>&1; then
    kill "${YOLO_PID}" >/dev/null 2>&1 || true
    wait "${YOLO_PID}" 2>/dev/null || true
  fi
  if [[ -n "${CAMERA_PID}" ]] && kill -0 "${CAMERA_PID}" >/dev/null 2>&1; then
    kill "${CAMERA_PID}" >/dev/null 2>&1 || true
    wait "${CAMERA_PID}" 2>/dev/null || true
  fi
  if [[ -n "${METRICS_PID}" ]] && kill -0 "${METRICS_PID}" >/dev/null 2>&1; then
    kill -INT "${METRICS_PID}" >/dev/null 2>&1 || true
    wait "${METRICS_PID}" 2>/dev/null || true
  fi
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

if [[ -n "${CAMERA_COMMAND}" ]]; then
  echo "启动 camera publisher: ${CAMERA_COMMAND}"
  bash -lc "${CAMERA_COMMAND}" &
  CAMERA_PID=$!
  sleep 2
fi

echo "Jetson YOLO demo 配置:"
echo "  ros_setup: ${ROS_SETUP}"
echo "  workspace_setup: ${WORKSPACE_SETUP}"
echo "  input_topic: ${INPUT_TOPIC}"
echo "  output_topic: ${OUTPUT_TOPIC}"
echo "  yolo_type: ${YOLO_TYPE}"
echo "  result_url: ${RESULT_URL:-<disabled>}"
echo "  source_host: ${SOURCE_HOST}"

echo "启动 Jetson metrics monitor"
python3 "${SCRIPT_DIR}/jetson_yolo_metrics.py" \
  --input-topic "${INPUT_TOPIC}" \
  --output-topic "${OUTPUT_TOPIC}" \
  --model-name "tensorrt_${YOLO_TYPE}" \
  --camera-device "${CAMERA_DEVICE}" \
  --run-id "${RUN_ID}" \
  --source-host "${SOURCE_HOST}" \
  --result-url "${RESULT_URL}" \
  --result-file "${RESULT_FILE}" \
  --tegrastats-command "${TEGRASTATS_COMMAND}" \
  --result-timeout-seconds "${RESULT_TIMEOUT_SECONDS}" \
  --result-max-retries "${RESULT_MAX_RETRIES}" \
  --result-retry-backoff-seconds "${RESULT_RETRY_BACKOFF_SECONDS}" \
  --spin-timeout-seconds "${SPIN_TIMEOUT_SECONDS}" &
METRICS_PID=$!
sleep 1

echo "启动 tensorrt_yolo launch"
ros2 launch tensorrt_yolo tensorrt_yolo.launch.xml \
  yolo_type:="${YOLO_TYPE}" \
  input_topic:="${INPUT_TOPIC}" \
  output_topic:="${OUTPUT_TOPIC}" \
  data_path:="${DATA_PATH}" \
  mode:="${MODE}" \
  gpu_id:="${GPU_ID}" &
YOLO_PID=$!

wait "${YOLO_PID}"
