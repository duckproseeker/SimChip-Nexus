#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"
STATE_DIR="${PI_GATEWAY_STATE_DIR:-${PROJECT_ROOT}/run_data/pi_gateway}"
STATE_FILE="${STATE_DIR}/bridge_state.json"

pkill -f 'ffmpeg .* -f v4l2 .* /dev/video' >/dev/null 2>&1 || true

if [[ -f "${STATE_FILE}" ]]; then
  python3 - <<PY
import json
from pathlib import Path

state_path = Path("${STATE_FILE}")
payload = json.loads(state_path.read_text(encoding="utf-8"))
payload["bridge_running"] = False
state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
PY
fi

echo "HDMI to UVC bridge stopped"
