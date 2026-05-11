#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
TIME_SYNC_ENABLED="${JETSON_SYNC_TIME_FROM_PI:-1}"

BUILD_DIR="${JETSON_CPP_DETECTOR_BUILD_DIR:-$HOME/duckpark_cpp_detector/build}"
BINARY_PATH="${JETSON_CPP_DETECTOR_BINARY:-${BUILD_DIR}/duckpark_cpp_detector}"
ENGINE_PATH="${JETSON_CPP_DETECTOR_ENGINE:-$HOME/yolo_ros2/module/yolov4-tiny.engine}"
LABEL_PATH="${JETSON_CPP_DETECTOR_LABELS:-$HOME/yolo_ros2/module/coco.names}"
SOURCE_URI="${JETSON_CPP_DETECTOR_SOURCE:-udp://0.0.0.0:5000}"
DECODER="${JETSON_CPP_DETECTOR_DECODER:-nvv4l2decoder}"
METRICS_FILE="${JETSON_METRICS_FILE:-$HOME/duckpark_non_ros_metrics.json}"
WINDOW_NAME="${JETSON_CPP_DETECTOR_WINDOW_NAME:-DuckPark C++ Detector}"
IGNORE_THRESH="${JETSON_CPP_DETECTOR_IGNORE_THRESH:-0.5}"
GPU_ID="${JETSON_CPP_DETECTOR_GPU_ID:-0}"
MAX_FRAMES="${JETSON_CPP_DETECTOR_MAX_FRAMES:-0}"
LOOP_FILE="${JETSON_CPP_DETECTOR_LOOP_FILE:-0}"
VERBOSE="${JETSON_CPP_DETECTOR_VERBOSE:-0}"
DISPLAY_FLAG="${JETSON_CPP_DETECTOR_DISPLAY:-auto}"
WRAP_NON_ROS_DEMO="${JETSON_CPP_DETECTOR_WRAP_NON_ROS_DEMO:-0}"
SWAP_RB="${JETSON_CPP_DETECTOR_SWAP_RB:-0}"

bool_flag() {
  local value
  value=$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')
  [[ "${value}" == "1" || "${value}" == "true" || "${value}" == "yes" || "${value}" == "on" ]]
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage:
  bash hil_runtime/jetson/scripts/start_jetson_cpp_detector.sh

Environment overrides:
  JETSON_CPP_DETECTOR_SOURCE            Input source, default udp://0.0.0.0:5000
  JETSON_CPP_DETECTOR_ENGINE            Engine path, default ~/yolo_ros2/module/yolov4-tiny.engine
  JETSON_CPP_DETECTOR_LABELS            Label file, default ~/yolo_ros2/module/coco.names
  JETSON_CPP_DETECTOR_DECODER           RTP decoder, default nvv4l2decoder
  JETSON_CPP_DETECTOR_DISPLAY           auto | 1 | 0
  JETSON_CPP_DETECTOR_SWAP_RB           1 to swap red and blue before inference/display
  JETSON_CPP_DETECTOR_WRAP_NON_ROS_DEMO 1 to reuse start_jetson_non_ros_demo.sh metrics wrapper

Examples:
  bash hil_runtime/jetson/scripts/start_jetson_cpp_detector.sh
  JETSON_CPP_DETECTOR_SOURCE="$HOME/ego_vehicle_camera.avi" \
  JETSON_CPP_DETECTOR_LOOP_FILE=1 \
  JETSON_CPP_DETECTOR_DISPLAY=1 \
  bash hil_runtime/jetson/scripts/start_jetson_cpp_detector.sh
EOF
  exit 0
fi

if bool_flag "${TIME_SYNC_ENABLED}"; then
  bash "${SCRIPT_DIR}/sync_jetson_time_from_pi.sh"
fi

if [[ ! -x "${BINARY_PATH}" ]]; then
  bash "${SCRIPT_DIR}/build_jetson_cpp_detector.sh"
fi

if [[ ! -x "${BINARY_PATH}" ]]; then
  echo "未找到 detector 二进制: ${BINARY_PATH}" >&2
  exit 1
fi

args=(
  --source "${SOURCE_URI}"
  --decoder "${DECODER}"
  --engine "${ENGINE_PATH}"
  --labels "${LABEL_PATH}"
  --metrics-file "${METRICS_FILE}"
  --window-name "${WINDOW_NAME}"
  --ignore-thresh "${IGNORE_THRESH}"
  --gpu-id "${GPU_ID}"
)

if [[ "${MAX_FRAMES}" != "0" ]]; then
  args+=(--max-frames "${MAX_FRAMES}")
fi

if bool_flag "${LOOP_FILE}"; then
  args+=(--loop-file)
fi

if bool_flag "${VERBOSE}"; then
  args+=(--verbose)
fi

if bool_flag "${SWAP_RB}"; then
  args+=(--swap-rb)
fi

if [[ "${DISPLAY_FLAG}" == "auto" ]]; then
  if [[ -n "${DISPLAY:-}" ]]; then
    args+=(--display)
  else
    args+=(--no-display)
  fi
elif bool_flag "${DISPLAY_FLAG}"; then
  if [[ -z "${DISPLAY:-}" ]]; then
    export DISPLAY=:0
  fi
  args+=(--display)
else
  args+=(--no-display)
fi

if bool_flag "${WRAP_NON_ROS_DEMO}"; then
  printf -v detector_command '%q ' "${BINARY_PATH}" "${args[@]}"
  export JETSON_DETECTOR_COMMAND="${detector_command% }"
  exec bash "${SCRIPT_DIR}/start_jetson_non_ros_demo.sh"
fi

exec "${BINARY_PATH}" "${args[@]}"
