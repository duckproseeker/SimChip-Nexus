#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
JETSON_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${JETSON_RUNTIME_ROOT}/.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"

SOURCE_DIR="${JETSON_CPP_DETECTOR_SOURCE_DIR:-${JETSON_RUNTIME_ROOT}/tools/jetson_cpp_detector}"
YOLO_WORKSPACE_DIR="${JETSON_YOLO_WORKSPACE_DIR:-$HOME/yolo_ros2}"
BUILD_DIR="${JETSON_CPP_DETECTOR_BUILD_DIR:-$HOME/duckpark_cpp_detector/build}"
TRT_YOLO_INCLUDE_DIR="${JETSON_TRT_YOLO_INCLUDE_DIR:-${YOLO_WORKSPACE_DIR}/src/perception/tensorrt_yolo/lib/include}"
TRT_YOLO_LIB_DIR="${JETSON_TRT_YOLO_LIB_DIR:-${YOLO_WORKSPACE_DIR}/install/tensorrt_yolo/lib}"
TRT_YOLO_PLUGIN_LIB_DIR="${JETSON_TRT_YOLO_PLUGIN_LIB_DIR:-${YOLO_WORKSPACE_DIR}/build/tensorrt_yolo}"

usage() {
  cat <<'EOF'
Usage:
  bash hil_runtime/jetson/scripts/build_jetson_cpp_detector.sh

Environment overrides:
  JETSON_CPP_DETECTOR_SOURCE_DIR     Source dir, default <repo>/hil_runtime/jetson/tools/jetson_cpp_detector
  JETSON_CPP_DETECTOR_BUILD_DIR      Build dir, default ~/duckpark_cpp_detector/build
  JETSON_YOLO_WORKSPACE_DIR          Existing YOLO ROS2 workspace, default ~/yolo_ros2
  JETSON_TRT_YOLO_INCLUDE_DIR        Directory containing trt_yolo.hpp
  JETSON_TRT_YOLO_LIB_DIR            Directory containing libyolo.so
  JETSON_TRT_YOLO_PLUGIN_LIB_DIR     Directory containing TensorRT YOLO plugins
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ ! -f "${SOURCE_DIR}/CMakeLists.txt" ]]; then
  echo "未找到 C++ detector 源码目录: ${SOURCE_DIR}" >&2
  exit 1
fi

if [[ ! -f "${TRT_YOLO_INCLUDE_DIR}/trt_yolo.hpp" ]]; then
  echo "未找到 trt_yolo.hpp: ${TRT_YOLO_INCLUDE_DIR}" >&2
  exit 1
fi

if [[ ! -e "${TRT_YOLO_LIB_DIR}/libyolo.so" ]]; then
  echo "未找到 libyolo.so: ${TRT_YOLO_LIB_DIR}" >&2
  exit 1
fi

if [[ ! -e "${TRT_YOLO_PLUGIN_LIB_DIR}/libmish_plugin.so" ]]; then
  echo "未找到 TensorRT YOLO plugin 库: ${TRT_YOLO_PLUGIN_LIB_DIR}" >&2
  exit 1
fi

mkdir -p "${BUILD_DIR}"

cmake \
  -S "${SOURCE_DIR}" \
  -B "${BUILD_DIR}" \
  -DTRT_YOLO_INCLUDE_DIR="${TRT_YOLO_INCLUDE_DIR}" \
  -DTRT_YOLO_LIB_DIR="${TRT_YOLO_LIB_DIR}" \
  -DTRT_YOLO_PLUGIN_LIB_DIR="${TRT_YOLO_PLUGIN_LIB_DIR}"

cmake --build "${BUILD_DIR}" -- -j"$(nproc)"

echo "构建完成: ${BUILD_DIR}/duckpark_cpp_detector"
