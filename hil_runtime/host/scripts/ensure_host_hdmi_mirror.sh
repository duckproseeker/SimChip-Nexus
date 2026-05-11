#!/usr/bin/env bash
set -euo pipefail

DISPLAY_VALUE="${DUCKPARK_HOST_DISPLAY:-${DISPLAY:-:1}}"
XAUTHORITY_PATH="${DUCKPARK_HOST_XAUTHORITY:-/home/du/.Xauthority}"
PRIMARY_OUTPUT="${DUCKPARK_HOST_PRIMARY_OUTPUT:-DP-0}"
HDMI_OUTPUT="${DUCKPARK_HOST_HDMI_OUTPUT:-HDMI-0}"
HDMI_MODE="${DUCKPARK_HOST_HDMI_MODE:-1920x1080}"
HDMI_RATE="${DUCKPARK_HOST_HDMI_RATE:-60}"
REQUIRE_CONNECTED="${DUCKPARK_HOST_HDMI_REQUIRE_CONNECTED:-0}"

usage() {
  cat <<'EOF'
Usage:
  bash hil_runtime/host/scripts/ensure_host_hdmi_mirror.sh

Environment overrides:
  DUCKPARK_HOST_DISPLAY               X11 display, default :1
  DUCKPARK_HOST_XAUTHORITY            Xauthority path, default /home/du/.Xauthority
  DUCKPARK_HOST_PRIMARY_OUTPUT        Primary display output, default DP-0
  DUCKPARK_HOST_HDMI_OUTPUT           HDMI output to mirror onto, default HDMI-0
  DUCKPARK_HOST_HDMI_MODE             HDMI mode, default 1920x1080
  DUCKPARK_HOST_HDMI_RATE             HDMI refresh rate, default 60
  DUCKPARK_HOST_HDMI_REQUIRE_CONNECTED
                                      Fail when HDMI is not physically connected, default 0
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

log() {
  printf '%s ensure-host-hdmi-mirror %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

bool_flag() {
  local value
  value=$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')
  [[ "${value}" == "1" || "${value}" == "true" || "${value}" == "yes" || "${value}" == "on" ]]
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_command xrandr

export DISPLAY="${DISPLAY_VALUE}"
export XAUTHORITY="${XAUTHORITY_PATH}"

XRANDR_QUERY="$(xrandr --query)"
if ! grep -q "^${PRIMARY_OUTPUT} connected" <<<"${XRANDR_QUERY}"; then
  echo "Primary display output is not connected: ${PRIMARY_OUTPUT}" >&2
  exit 1
fi

if ! grep -q "^${HDMI_OUTPUT} connected" <<<"${XRANDR_QUERY}"; then
  if bool_flag "${REQUIRE_CONNECTED}"; then
    echo "HDMI output is not connected: ${HDMI_OUTPUT}" >&2
    exit 1
  fi
  log "skip: HDMI output ${HDMI_OUTPUT} is not connected"
  exit 0
fi

MONITORS_OUTPUT="$(xrandr --listmonitors 2>/dev/null || true)"
if grep -q "[[:space:]]${HDMI_OUTPUT}\$" <<<"${MONITORS_OUTPUT}"; then
  log "already active: ${HDMI_OUTPUT} is present in xrandr --listmonitors"
  exit 0
fi

log "activating mirror ${HDMI_OUTPUT} -> ${PRIMARY_OUTPUT} mode=${HDMI_MODE}@${HDMI_RATE}"
xrandr \
  --output "${HDMI_OUTPUT}" \
  --mode "${HDMI_MODE}" \
  --rate "${HDMI_RATE}" \
  --same-as "${PRIMARY_OUTPUT}"

MONITORS_OUTPUT="$(xrandr --listmonitors 2>/dev/null || true)"
if ! grep -q "[[:space:]]${HDMI_OUTPUT}\$" <<<"${MONITORS_OUTPUT}"; then
  echo "HDMI output ${HDMI_OUTPUT} is connected but did not become an active monitor" >&2
  exit 1
fi

log "mirror ready: ${PRIMARY_OUTPUT} + ${HDMI_OUTPUT}"
