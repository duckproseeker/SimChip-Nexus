#!/usr/bin/env bash
set -euo pipefail

PI_TIME_URL="${JETSON_PI_TIME_URL:-http://192.168.50.1:18765/healthz}"
TIME_SYNC_ENABLED="${JETSON_SYNC_TIME_FROM_PI:-1}"
TIME_SYNC_STRICT="${JETSON_TIME_SYNC_STRICT:-0}"
MAX_ALLOWED_DRIFT_SECONDS="${JETSON_MAX_TIME_DRIFT_SECONDS:-15}"
PYTHON_BIN="${JETSON_TIME_SYNC_PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage:
  bash hil_runtime/jetson/scripts/sync_jetson_time_from_pi.sh

Environment overrides:
  JETSON_SYNC_TIME_FROM_PI      Enable sync attempt, default 1
  JETSON_TIME_SYNC_STRICT       Fail when sync cannot complete, default 0
  JETSON_PI_TIME_URL            Pi URL used to read HTTP Date header, default http://192.168.50.1:18765/healthz
  JETSON_MAX_TIME_DRIFT_SECONDS Skip date set when drift is already within threshold, default 15
  JETSON_TIME_SYNC_PYTHON_BIN   Python interpreter used for header parsing, default python3
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

log() {
  printf '%s jetson-time-sync %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
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

handle_failure() {
  local message="$1"
  if bool_flag "${TIME_SYNC_STRICT}"; then
    echo "${message}" >&2
    exit 1
  fi
  log "warning: ${message}"
  exit 0
}

if ! bool_flag "${TIME_SYNC_ENABLED}"; then
  log "skip: disabled by JETSON_SYNC_TIME_FROM_PI=${TIME_SYNC_ENABLED}"
  exit 0
fi

require_command "${PYTHON_BIN}"
require_command date
require_command sudo

read -r PI_REMOTE_EPOCH PI_REMOTE_ISO < <(
  "${PYTHON_BIN}" - "${PI_TIME_URL}" <<'PY'
import email.utils
import sys
import urllib.request

url = sys.argv[1]
resp = urllib.request.urlopen(url, timeout=3.0)
date_header = resp.headers.get("Date")
if not date_header:
    raise SystemExit(2)
dt = email.utils.parsedate_to_datetime(date_header)
print(int(dt.timestamp()), dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
PY
) || handle_failure "failed to read Pi time header from ${PI_TIME_URL}"

LOCAL_EPOCH="$(date -u +%s)"
DRIFT_SECONDS="$("${PYTHON_BIN}" - <<PY
local_epoch = int("${LOCAL_EPOCH}")
remote_epoch = int("${PI_REMOTE_EPOCH}")
print(abs(remote_epoch - local_epoch))
PY
)"

log "pi_time=${PI_REMOTE_ISO} local_epoch=${LOCAL_EPOCH} drift_seconds=${DRIFT_SECONDS}"

if [[ "${DRIFT_SECONDS}" -le "${MAX_ALLOWED_DRIFT_SECONDS}" ]]; then
  log "skip: local clock already within ${MAX_ALLOWED_DRIFT_SECONDS}s"
  exit 0
fi

DATE_BIN="$(command -v date)"

if sudo -n "${DATE_BIN}" -u +%s >/dev/null 2>&1; then
  sudo "${DATE_BIN}" -u -s "@${PI_REMOTE_EPOCH}" >/dev/null
  log "synced using passwordless sudo"
  exit 0
fi

if [[ -t 0 ]]; then
  log "sync requires sudo password; prompting on tty"
  sudo "${DATE_BIN}" -u -s "@${PI_REMOTE_EPOCH}" >/dev/null || handle_failure "sudo date command failed"
  log "synced using interactive sudo"
  exit 0
fi

handle_failure "sudo password is required to sync time on Jetson; rerun from an interactive shell or enable passwordless sudo"
