#!/usr/bin/env bash
set -euo pipefail

DUCKPARK_HOST_SSH_HOST="${DUCKPARK_HOST_SSH_HOST:-}"
DUCKPARK_HOST_SSH_USER="${DUCKPARK_HOST_SSH_USER:-}"
DUCKPARK_HOST_SSH_PORT="${DUCKPARK_HOST_SSH_PORT:-22}"
DUCKPARK_HOST_SRC_ROOT="${DUCKPARK_HOST_SRC_ROOT:-}"
DUCKPARK_HOST_SSH_BIN="${DUCKPARK_HOST_SSH_BIN:-ssh}"
DUCKPARK_HOST_SSH_STRICT_HOST_KEY_CHECKING="${DUCKPARK_HOST_SSH_STRICT_HOST_KEY_CHECKING:-accept-new}"
DUCKPARK_HOST_SSH_IDENTITY_FILE="${DUCKPARK_HOST_SSH_IDENTITY_FILE:-}"

duckpark_host_ssh_require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

duckpark_host_ssh_require_text() {
  local value="$1"
  local label="$2"
  if [[ -z "${value}" ]]; then
    echo "${label} is required" >&2
    exit 1
  fi
}

duckpark_host_ssh_init() {
  duckpark_host_ssh_require_command "${DUCKPARK_HOST_SSH_BIN}"
  duckpark_host_ssh_require_text "${DUCKPARK_HOST_SSH_HOST}" "DUCKPARK_HOST_SSH_HOST"
  duckpark_host_ssh_require_text "${DUCKPARK_HOST_SSH_USER}" "DUCKPARK_HOST_SSH_USER"

  if [[ -z "${DUCKPARK_HOST_SRC_ROOT}" ]]; then
    DUCKPARK_HOST_SRC_ROOT="/home/${DUCKPARK_HOST_SSH_USER}/ros2-humble/src"
  fi

  DUCKPARK_HOST_SSH_TARGET="${DUCKPARK_HOST_SSH_USER}@${DUCKPARK_HOST_SSH_HOST}"
  DUCKPARK_HOST_SSH_ARGS=(
    -p "${DUCKPARK_HOST_SSH_PORT}"
    -o BatchMode=yes
    -o "StrictHostKeyChecking=${DUCKPARK_HOST_SSH_STRICT_HOST_KEY_CHECKING}"
  )

  if [[ -z "${DUCKPARK_HOST_SSH_IDENTITY_FILE}" ]] && [[ -f "${HOME}/.ssh/id_ed25519_duckpark" ]]; then
    DUCKPARK_HOST_SSH_IDENTITY_FILE="${HOME}/.ssh/id_ed25519_duckpark"
  fi

  if [[ -n "${DUCKPARK_HOST_SSH_IDENTITY_FILE}" ]]; then
    DUCKPARK_HOST_SSH_ARGS+=(-i "${DUCKPARK_HOST_SSH_IDENTITY_FILE}" -o IdentitiesOnly=yes)
  fi
}

duckpark_host_ssh() {
  "${DUCKPARK_HOST_SSH_BIN}" \
    "${DUCKPARK_HOST_SSH_ARGS[@]}" \
    "${DUCKPARK_HOST_SSH_TARGET}" \
    "$@"
}
