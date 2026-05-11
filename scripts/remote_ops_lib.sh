#!/usr/bin/env bash

set -euo pipefail

if [[ "${REMOTE_OPS_LIB_SOURCED:-0}" == "1" ]]; then
  return 0 2>/dev/null || exit 0
fi
REMOTE_OPS_LIB_SOURCED=1

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${REMOTE_HOST:-192.168.110.151}"
REMOTE_USER="${REMOTE_USER:-du}"
REMOTE_PORT="${REMOTE_PORT:-22}"
REMOTE_CONTAINER="${REMOTE_CONTAINER:-ros2-dev}"
REMOTE_PROJECT_ROOT="${REMOTE_PROJECT_ROOT:-/ros2_ws/src/carla_web_platform}"
REMOTE_API_BASE_URL="${REMOTE_API_BASE_URL:-http://${REMOTE_HOST}:8000}"
REMOTE_PASSWORD="${REMOTE_PASSWORD:-}"
EXPECT_TIMEOUT="${EXPECT_TIMEOUT:-600}"

remote_log() {
  printf '[remote-ops] %s\n' "$*"
}

require_remote_ops_cmds() {
  local missing=0
  local cmd
  for cmd in expect python3 tar scp ssh; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      printf '[remote-ops] missing command: %s\n' "$cmd" >&2
      missing=1
    fi
  done
  if (( missing != 0 )); then
    return 1
  fi
}

ensure_remote_password() {
  if [[ -n "${REMOTE_PASSWORD}" ]]; then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    printf '[remote-ops] REMOTE_PASSWORD is required in non-interactive mode\n' >&2
    return 1
  fi
  read -r -s -p "Remote password for ${REMOTE_USER}@${REMOTE_HOST}: " REMOTE_PASSWORD
  printf '\n'
}

expect_spawn() {
  ensure_remote_password
  local quoted_command=""
  printf -v quoted_command '%q ' "$@"
  REMOTE_PASSWORD="$REMOTE_PASSWORD" EXPECT_TIMEOUT="$EXPECT_TIMEOUT" EXPECT_COMMAND="$quoted_command" expect <<'EOF'
set timeout $env(EXPECT_TIMEOUT)
set password $env(REMOTE_PASSWORD)
eval spawn -noecho $env(EXPECT_COMMAND)
expect {
  -re {(?i)yes/no} {
    send -- "yes\r"
    exp_continue
  }
  -re {(?i)password:} {
    send -- "$password\r"
    exp_continue
  }
  eof
}
lassign [wait] _pid _spawn_id _os_error exit_code
exit $exit_code
EOF
}

remote_ssh() {
  local remote_command="$1"
  expect_spawn ssh -p "$REMOTE_PORT" -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "$remote_command"
}

remote_scp() {
  expect_spawn scp -P "$REMOTE_PORT" -o StrictHostKeyChecking=no "$@"
}

_b64_no_wrap() {
  python3 -c 'import base64,sys; sys.stdout.write(base64.b64encode(sys.stdin.buffer.read()).decode("ascii"))'
}

remote_host_bash() {
  local script="$1"
  local encoded
  local python_cmd
  encoded="$(printf '%s' "$script" | _b64_no_wrap)"
  python_cmd="import base64,subprocess; script=base64.b64decode('${encoded}').decode('utf-8'); subprocess.run(['bash','-lc',script], check=True)"
  remote_ssh "python3 -c $(printf '%q' "$python_cmd")"
}

remote_container_bash() {
  local script="$1"
  local encoded
  local python_cmd
  encoded="$(printf '%s' "$script" | _b64_no_wrap)"
  python_cmd="import base64,subprocess; script=base64.b64decode('${encoded}').decode('utf-8'); subprocess.run(['docker','exec','${REMOTE_CONTAINER}','bash','-lc',script], check=True)"
  remote_ssh "python3 -c $(printf '%q' "$python_cmd")"
}

stop_remote_services() {
  local stop_script
  stop_script="$(cat <<'PY'
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path


def find_matching_pids(pattern: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"pgrep failed for pattern {pattern!r}: {result.stderr.strip()}")
    if result.returncode == 1:
        return []

    current_pid = os.getpid()
    parent_pid = os.getppid()
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid = int(line)
        if pid not in (current_pid, parent_pid):
            pids.append(pid)
    return pids


def terminate_patterns(patterns: list[str], timeout_seconds: float) -> dict[str, list[int]]:
    pending: set[int] = set()
    for pattern in patterns:
        pending.update(find_matching_pids(pattern))

    for pid in pending:
        os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + timeout_seconds
    while pending and time.monotonic() < deadline:
        time.sleep(0.5)
        pending = {pid for pid in pending if Path(f"/proc/{pid}").exists()}

    for pid in list(pending):
        os.kill(pid, signal.SIGKILL)

    return {
        "api": find_matching_pids(api_patterns[0]) or find_matching_pids(api_patterns[1]),
        "executor": find_matching_pids(executor_patterns[0]) or find_matching_pids(executor_patterns[1]),
        "workers": find_matching_pids(worker_patterns[0]) or find_matching_pids(worker_patterns[1]),
    }


api_patterns = [
    "".join(["python3 -m", " uvicorn app.api.main:app --host 0.0.0.0 --port 8000"]),
    "".join(["uvicorn", " app.api.main:app --host 0.0.0.0 --port 8000"]),
]
executor_patterns = [
    "".join(["python3 -m", " app.executor.service"]),
    "app.executor.service",
]
worker_patterns = [
    "".join(["python3 -m", " app.executor.sensor_recorder_worker"]),
    "app.executor.sensor_recorder_worker",
]

print(
    json.dumps(
        {"remaining": terminate_patterns(api_patterns + executor_patterns + worker_patterns, timeout_seconds=10.0)},
        ensure_ascii=False,
    )
)
PY
)"

  remote_container_bash "
set -euo pipefail
cd $(printf '%q' "$REMOTE_PROJECT_ROOT")
python3 - <<'PY'
${stop_script}
PY
"
}

restart_remote_services() {
  local restart_script
  restart_script="$(cat <<'PY'
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def load_launch_env(project_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env_file = project_root / ".env.local"
    if not env_file.exists():
        return env

    result = subprocess.run(
        ["bash", "-lc", "set -a; source ./.env.local; env -0"],
        cwd=project_root,
        check=True,
        capture_output=True,
    )
    for chunk in result.stdout.split(b"\0"):
        if not chunk or b"=" not in chunk:
            continue
        key, value = chunk.split(b"=", 1)
        env[key.decode("utf-8", errors="ignore")] = value.decode("utf-8", errors="ignore")
    return env


def find_matching_pids(pattern: str) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"pgrep failed for pattern {pattern!r}: {result.stderr.strip()}")
    if result.returncode == 1:
        return []

    current_pid = os.getpid()
    parent_pid = os.getppid()
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid = int(line)
        if pid not in (current_pid, parent_pid):
            pids.append(pid)
    return pids


def terminate_patterns(patterns: list[str], timeout_seconds: float) -> None:
    pending: set[int] = set()
    for pattern in patterns:
        pending.update(find_matching_pids(pattern))

    for pid in pending:
        os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + timeout_seconds
    while pending and time.monotonic() < deadline:
        time.sleep(0.5)
        pending = {pid for pid in pending if Path(f"/proc/{pid}").exists()}

    for pid in list(pending):
        os.kill(pid, signal.SIGKILL)


def spawn_process(command: list[str], project_root: Path, env: dict[str, str], log_path: Path) -> int:
    log_handle = log_path.open("ab")
    try:
        process = subprocess.Popen(
            command,
            cwd=project_root,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return process.pid
    finally:
        log_handle.close()


project_root = Path(os.environ["DUCKPARK_REMOTE_PROJECT_ROOT"]).resolve()
api_log_path = Path("/tmp/carla_api_restore.log")
executor_log_path = Path("/tmp/carla_executor_restore.log")

api_patterns = [
    "".join(["python3 -m", " uvicorn app.api.main:app --host 0.0.0.0 --port 8000"]),
    "".join(["uvicorn", " app.api.main:app --host 0.0.0.0 --port 8000"]),
]
executor_patterns = [
    "".join(["python3 -m", " app.executor.service"]),
]
worker_patterns = [
    "".join(["python3 -m", " app.executor.sensor_recorder_worker"]),
    "app.executor.sensor_recorder_worker",
]

terminate_patterns(api_patterns + executor_patterns + worker_patterns, timeout_seconds=10.0)

launch_env = load_launch_env(project_root)
launch_env["PYTHONDONTWRITEBYTECODE"] = "1"
launch_env["PYTHONUNBUFFERED"] = "1"

api_pid = spawn_process(
    [sys.executable, "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"],
    project_root,
    launch_env,
    api_log_path,
)
executor_pid = spawn_process(
    [sys.executable, "-m", "app.executor.service"],
    project_root,
    launch_env,
    executor_log_path,
)

time.sleep(4)

running = {
    "api": find_matching_pids(api_patterns[0]) or find_matching_pids(api_patterns[1]),
    "executor": find_matching_pids(executor_patterns[0]),
}
if not running["api"]:
    raise RuntimeError("API process did not stay up after restart")
if not running["executor"]:
    raise RuntimeError("executor process did not stay up after restart")

print(
    json.dumps(
        {
            "requested": {"api_pid": api_pid, "executor_pid": executor_pid},
            "running": running,
        },
        ensure_ascii=False,
    )
)
PY
)"

  remote_container_bash "
set -euo pipefail
cd $(printf '%q' "$REMOTE_PROJECT_ROOT")
export DUCKPARK_REMOTE_PROJECT_ROOT=$(printf '%q' "$REMOTE_PROJECT_ROOT")
python3 - <<'PY'
${restart_script}
PY
"
}

ensure_remote_carla_ready() {
  remote_log "checking CARLA availability on ${REMOTE_HOST}:2000"
  if remote_host_bash "
python3 - <<'PY'
import socket
import sys

sock = socket.socket()
sock.settimeout(2.0)
try:
    sock.connect(('127.0.0.1', 2000))
except OSError:
    sys.exit(1)
finally:
    sock.close()

print('carla-port-ok')
PY
"; then
    return 0
  fi

  remote_log "CARLA not reachable; starting ~/startCarla.sh"
  remote_host_bash "
set -euo pipefail
bash ~/startCarla.sh
"

  remote_log "waiting for CARLA to accept connections"
  remote_host_bash "
python3 - <<'PY'
import socket
import sys
import time

deadline = time.time() + 90.0
last_error = None
while time.time() < deadline:
    sock = socket.socket()
    sock.settimeout(2.0)
    try:
        sock.connect(('127.0.0.1', 2000))
    except OSError as exc:
        last_error = exc
        time.sleep(1.0)
    else:
        print('carla-port-ok')
        sys.exit(0)
    finally:
        sock.close()

print(f'carla-port-not-ready: {last_error}')
sys.exit(1)
PY
"
}

run_remote_smoke() {
  local mode="$1"
  python3 "$PROJECT_ROOT/scripts/remote_smoke.py" --base-url "$REMOTE_API_BASE_URL" --mode "$mode"
}
