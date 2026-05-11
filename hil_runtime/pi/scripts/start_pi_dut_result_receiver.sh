#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"

export PROJECT_ROOT
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

ARGS=()

if [[ -n "${PI_GATEWAY_DUT_RESULT_RECEIVER_HOST:-}" ]]; then
  ARGS+=(--host "${PI_GATEWAY_DUT_RESULT_RECEIVER_HOST}")
fi

if [[ -n "${PI_GATEWAY_DUT_RESULT_RECEIVER_PORT:-}" ]]; then
  ARGS+=(--port "${PI_GATEWAY_DUT_RESULT_RECEIVER_PORT}")
fi

if [[ -n "${PI_GATEWAY_STATE_DIR:-}" ]]; then
  ARGS+=(--state-dir "${PI_GATEWAY_STATE_DIR}")
fi

if [[ -n "${PI_GATEWAY_DUT_RESULT_FILE:-}" ]]; then
  ARGS+=(--result-file "${PI_GATEWAY_DUT_RESULT_FILE}")
fi

exec python3 -m app.hil.dut_result_receiver "${ARGS[@]}" "$@"
