#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"
TIME_SYNC_ENABLED="${JETSON_SYNC_TIME_FROM_PI:-1}"

RTP_PORT="${JETSON_RTP_PORT:-5000}"
RTP_HOST="${JETSON_RTP_HOST:-0.0.0.0}"
INPUT_TOPIC="${JETSON_INPUT_TOPIC:-/image_raw}"
OUTPUT_TOPIC="${JETSON_OUTPUT_TOPIC:-/duckpark/rois}"
FRAME_ID="${JETSON_RTP_FRAME_ID:-camera}"
RTP_DECODER="${JETSON_RTP_DECODER:-nvv4l2decoder}"
RESULT_URL="${JETSON_RESULT_URL:-http://192.168.50.1:18765/dut-results}"
YOLO_TYPE="${JETSON_YOLO_TYPE:-yolov5s}"

usage() {
  cat <<'EOF'
Usage:
  bash hil_runtime/jetson/scripts/start_jetson_hil_pipeline.sh

Environment overrides:
  JETSON_RTP_PORT                  RTP listen port, default 5000
  JETSON_RTP_HOST                  RTP bind address, default 0.0.0.0
  JETSON_RTP_FRAME_ID              ROS frame_id for published images
  JETSON_RTP_DECODER               Decoder for RTP camera node, default nvv4l2decoder
  JETSON_INPUT_TOPIC               ROS image topic, default /image_raw
  JETSON_OUTPUT_TOPIC              YOLO output topic, default /duckpark/rois
  JETSON_RESULT_URL                Pi result receiver URL
  JETSON_YOLO_TYPE                 tensorrt_yolo model name, default yolov5s
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "${TIME_SYNC_ENABLED,,}" == "1" || "${TIME_SYNC_ENABLED,,}" == "true" || "${TIME_SYNC_ENABLED,,}" == "yes" || "${TIME_SYNC_ENABLED,,}" == "on" ]]; then
  bash "${SCRIPT_DIR}/sync_jetson_time_from_pi.sh"
fi

export PROJECT_ROOT
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"
export JETSON_RESULT_URL="${RESULT_URL}"
export JETSON_INPUT_TOPIC="${INPUT_TOPIC}"
export JETSON_OUTPUT_TOPIC="${OUTPUT_TOPIC}"

CAMERA_COMMAND=$(
  printf 'cd %q && export PYTHONPATH=%q && python3 -m app.hil.jetson_rtp_camera_node --host %q --port %q --topic %q --frame-id %q' \
    "${PROJECT_ROOT}" \
    "${PROJECT_ROOT}:${PYTHONPATH}" \
    "${RTP_HOST}" \
    "${RTP_PORT}" \
    "${INPUT_TOPIC}" \
    "${FRAME_ID}"
)
CAMERA_COMMAND+=" --decoder ${RTP_DECODER}"
export JETSON_CAMERA_COMMAND="${CAMERA_COMMAND}"

echo "Jetson HIL pipeline status:"
echo "  rtp_source: udp://${RTP_HOST}:${RTP_PORT}"
echo "  image_topic: ${INPUT_TOPIC}"
echo "  yolo_topic: ${OUTPUT_TOPIC}"
echo "  rtp_decoder: ${RTP_DECODER}"
echo "  model: tensorrt_${YOLO_TYPE}"
echo "  result_url: ${RESULT_URL}"
echo "  note: FPS 和 latency 会由 jetson_yolo_metrics.py 持续输出"

exec bash "${SCRIPT_DIR}/start_jetson_tensorrt_yolo_demo.sh"
