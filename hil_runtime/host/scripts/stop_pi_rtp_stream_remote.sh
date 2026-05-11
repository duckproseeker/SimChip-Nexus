#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${DUCKPARK_PI_HOST:-}"
PI_USER="${DUCKPARK_PI_USER:-}"
PI_PORT="${DUCKPARK_PI_PORT:-22}"
SSH_BIN="${DUCKPARK_PI_SSH_BIN:-ssh}"
SSH_STRICT_HOST_KEY_CHECKING="${DUCKPARK_PI_SSH_STRICT_HOST_KEY_CHECKING:-accept-new}"
SSH_IDENTITY_FILE="${DUCKPARK_PI_SSH_IDENTITY_FILE:-}"

usage() {
  cat <<'EOF'
Usage:
  bash hil_runtime/host/scripts/stop_pi_rtp_stream_remote.sh

Required environment:
  DUCKPARK_PI_HOST                  Pi SSH host
  DUCKPARK_PI_USER                  Pi SSH user

Optional environment:
  DUCKPARK_PI_PORT                  Pi SSH port, default 22
  DUCKPARK_PI_SSH_BIN               SSH binary, default ssh
  DUCKPARK_PI_SSH_STRICT_HOST_KEY_CHECKING
                                     SSH StrictHostKeyChecking mode, default accept-new
  DUCKPARK_PI_SSH_IDENTITY_FILE     Optional SSH identity file. If unset, the wrapper will
                                     reuse ~/.ssh/id_ed25519_duckpark when present.

Notes:
  - This sends SIGINT to the Pi RTP wrapper script first so its trap can stop GStreamer cleanly.
  - It also stops the Pi DUT result receiver and gateway heartbeat agent.
  - As a fallback it also stops matching gst-launch RTP sender pipelines.
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_text() {
  local value="$1"
  local label="$2"
  if [[ -z "${value}" ]]; then
    echo "${label} is required" >&2
    exit 1
  fi
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

require_command "${SSH_BIN}"
require_text "${PI_HOST}" "DUCKPARK_PI_HOST"
require_text "${PI_USER}" "DUCKPARK_PI_USER"

SSH_TARGET="${PI_USER}@${PI_HOST}"
declare -a SSH_ARGS=(
  -p "${PI_PORT}"
  -o BatchMode=yes
  -o "StrictHostKeyChecking=${SSH_STRICT_HOST_KEY_CHECKING}"
)

if [[ -z "${SSH_IDENTITY_FILE}" ]] && [[ -f "${HOME}/.ssh/id_ed25519_duckpark" ]]; then
  SSH_IDENTITY_FILE="${HOME}/.ssh/id_ed25519_duckpark"
fi

if [[ -n "${SSH_IDENTITY_FILE}" ]]; then
  SSH_ARGS+=(-i "${SSH_IDENTITY_FILE}" -o IdentitiesOnly=yes)
fi

"${SSH_BIN}" \
  "${SSH_ARGS[@]}" \
  "${SSH_TARGET}" \
  bash -s <<'EOF'
set -euo pipefail

WRAPPER_PATTERN='[s]tart_pi_hdmi_rtp_stream.sh'
GST_PATTERN='[g]st-launch-1.0.*rtph264pay.*udpsink'
RECEIVER_PATTERN='[d]ut_result_receiver'
AGENT_PATTERN='[g]ateway_agent'

pkill -INT -f "${WRAPPER_PATTERN}" >/dev/null 2>&1 || true
pkill -f "${GST_PATTERN}" >/dev/null 2>&1 || true
pkill -INT -f "${RECEIVER_PATTERN}" >/dev/null 2>&1 || true
pkill -INT -f "${AGENT_PATTERN}" >/dev/null 2>&1 || true

for _ in $(seq 1 10); do
  if ! pgrep -f "${WRAPPER_PATTERN}" >/dev/null 2>&1 && \
     ! pgrep -f "${GST_PATTERN}" >/dev/null 2>&1 && \
     ! pgrep -f "${RECEIVER_PATTERN}" >/dev/null 2>&1 && \
     ! pgrep -f "${AGENT_PATTERN}" >/dev/null 2>&1; then
    echo "pi_gateway_stack_stopped"
    exit 0
  fi
  sleep 0.5
done

pkill -TERM -f "${WRAPPER_PATTERN}" >/dev/null 2>&1 || true
pkill -TERM -f "${GST_PATTERN}" >/dev/null 2>&1 || true
pkill -TERM -f "${RECEIVER_PATTERN}" >/dev/null 2>&1 || true
pkill -TERM -f "${AGENT_PATTERN}" >/dev/null 2>&1 || true
sleep 1

if pgrep -f "${WRAPPER_PATTERN}" >/dev/null 2>&1; then
  echo "Pi RTP wrapper is still running after stop request" >&2
  exit 1
fi

if pgrep -f "${GST_PATTERN}" >/dev/null 2>&1; then
  echo "Pi RTP gst-launch pipeline is still running after stop request" >&2
  exit 1
fi

if pgrep -f "${RECEIVER_PATTERN}" >/dev/null 2>&1; then
  echo "Pi DUT result receiver is still running after stop request" >&2
  exit 1
fi

if pgrep -f "${AGENT_PATTERN}" >/dev/null 2>&1; then
  echo "Pi gateway agent is still running after stop request" >&2
  exit 1
fi

echo "pi_gateway_stack_stopped"
EOF
