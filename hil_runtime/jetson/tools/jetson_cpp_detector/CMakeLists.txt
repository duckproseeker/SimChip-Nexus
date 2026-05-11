cmake_minimum_required(VERSION 3.16)
project(duckpark_cpp_detector LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(TRT_YOLO_INCLUDE_DIR "" CACHE PATH "Directory containing trt_yolo.hpp")
set(TRT_YOLO_LIB_DIR "" CACHE PATH "Directory containing libyolo.so")
set(TRT_YOLO_PLUGIN_LIB_DIR "" CACHE PATH "Directory containing TensorRT YOLO plugin shared libraries")

if(NOT TRT_YOLO_INCLUDE_DIR)
  message(FATAL_ERROR "TRT_YOLO_INCLUDE_DIR is required")
endif()

if(NOT TRT_YOLO_LIB_DIR)
  message(FATAL_ERROR "TRT_YOLO_LIB_DIR is required")
endif()

if(NOT TRT_YOLO_PLUGIN_LIB_DIR)
  message(FATAL_ERROR "TRT_YOLO_PLUGIN_LIB_DIR is required")
endif()

find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)

pkg_check_modules(OPENCV REQUIRED opencv4)

find_library(TRT_YOLO_LIBRARY NAMES yolo HINTS "${TRT_YOLO_LIB_DIR}" REQUIRED NO_DEFAULT_PATH)
find_library(MISH_PLUGIN_LIBRARY NAMES mish_plugin HINTS "${TRT_YOLO_PLUGIN_LIB_DIR}" REQUIRED NO_DEFAULT_PATH)
find_library(YOLO_LAYER_PLUGIN_LIBRARY NAMES yolo_layer_plugin HINTS "${TRT_YOLO_PLUGIN_LIB_DIR}" REQUIRED NO_DEFAULT_PATH)
find_library(NMS_PLUGIN_LIBRARY NAMES nms_plugin HINTS "${TRT_YOLO_PLUGIN_LIB_DIR}" REQUIRED NO_DEFAULT_PATH)
find_library(NVINFER_LIBRARY NAMES nvinfer REQUIRED)
find_library(NVONNXPARSER_LIBRARY NAMES nvonnxparser REQUIRED)
find_library(NVINFER_PLUGIN_LIBRARY NAMES nvinfer_plugin REQUIRED)
find_library(CUDART_LIBRARY NAMES cudart HINTS
  /usr/local/cuda/lib64
  /usr/local/cuda/targets/aarch64-linux/lib
  REQUIRED
)

add_executable(duckpark_cpp_detector
  src/main.cpp
)

target_include_directories(duckpark_cpp_detector PRIVATE
  "${TRT_YOLO_INCLUDE_DIR}"
  ${OPENCV_INCLUDE_DIRS}
  /usr/local/cuda/include
)

target_compile_options(duckpark_cpp_detector PRIVATE
  -Wall
  -Wextra
  -Wpedantic
)

target_link_libraries(duckpark_cpp_detector PRIVATE
  "${TRT_YOLO_LIBRARY}"
  "${MISH_PLUGIN_LIBRARY}"
  "${YOLO_LAYER_PLUGIN_LIBRARY}"
  "${NMS_PLUGIN_LIBRARY}"
  "${NVINFER_LIBRARY}"
  "${NVONNXPARSER_LIBRARY}"
  "${NVINFER_PLUGIN_LIBRARY}"
  "${CUDART_LIBRARY}"
  Threads::Threads
  ${CMAKE_DL_LIBS}
  ${OPENCV_LIBRARIES}
)

set(_duckpark_runtime_paths "${TRT_YOLO_LIB_DIR};${TRT_YOLO_PLUGIN_LIB_DIR}")

set_target_properties(duckpark_cpp_detector PROPERTIES
  BUILD_RPATH "${_duckpark_runtime_paths}"
  INSTALL_RPATH "${_duckpark_runtime_paths}"
)
