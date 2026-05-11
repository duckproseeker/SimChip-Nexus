#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
ENV_FILE="${PROJECT_ROOT}/.env.local"

export PROJECT_ROOT
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

usage() {
  cat <<'EOF'
用法:
  bash scripts/start_platform.sh [options]

可选参数:
  --api-host <host>                API 监听地址，默认读取 API_HOST 或 0.0.0.0
  --api-port <port>                API 监听端口，默认读取 API_PORT 或 8000
  --carla-host <host>              CARLA server 地址
  --carla-port <port>              CARLA RPC 端口
  --traffic-manager-port <port>    Traffic Manager 端口
  --with-executor                  显式启动 executor，覆盖 .env.local 中的 START_EXECUTOR=false
  --no-executor                    仅启动 Web/API，不启动 executor
  --help                           输出帮助

示例:
  bash scripts/start_platform.sh --carla-host 127.0.0.1 --carla-port 2000 --traffic-manager-port 8010
  bash scripts/start_platform.sh --api-host 0.0.0.0 --api-port 18000 --no-executor
EOF
}

require_arg_value() {
  if [[ $# -lt 2 || -z "${2:-}" ]]; then
    echo "参数 $1 缺少取值" >&2
    usage >&2
    exit 1
  fi
}

while (($# > 0)); do
  case "$1" in
    --api-host)
      require_arg_value "$@"
      export API_HOST="$2"
      shift 2
      ;;
    --api-port)
      require_arg_value "$@"
      export API_PORT="$2"
      shift 2
      ;;
    --carla-host)
      require_arg_value "$@"
      export CARLA_HOST="$2"
      shift 2
      ;;
    --carla-port)
      require_arg_value "$@"
      export CARLA_PORT="$2"
      shift 2
      ;;
    --traffic-manager-port)
      require_arg_value "$@"
      export TRAFFIC_MANAGER_PORT="$2"
      shift 2
      ;;
    --no-executor)
      export START_EXECUTOR=false
      shift
      ;;
    --with-executor)
      export START_EXECUTOR=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${CARLA_HOST:-}" ]]; then
  cat >&2 <<'EOF'
缺少 CARLA_HOST。

建议提供下面至少一组配置：
  CARLA_HOST=127.0.0.1
  CARLA_PORT=2000
  TRAFFIC_MANAGER_PORT=8010

可以通过以下任一方式传入：
  1. 项目根目录下的 .env.local
  2. shell 环境变量
  3. 启动参数，例如:
     bash scripts/start_platform.sh --carla-host 127.0.0.1 --carla-port 2000 --traffic-manager-port 8010
EOF
  exit 1
fi

EXECUTOR_PID=""
START_EXECUTOR_VALUE="${START_EXECUTOR:-true}"
START_EXECUTOR_NORMALIZED=$(printf '%s' "${START_EXECUTOR_VALUE}" | tr '[:upper:]' '[:lower:]')

# Avoid multiple API / executor copies competing for the same run queue.
pkill -f "uvicorn app.api.main:app" >/dev/null 2>&1 || true
pkill -f "python3 -m app.executor.service" >/dev/null 2>&1 || true

if [[ "${START_EXECUTOR_NORMALIZED}" == "true" || "${START_EXECUTOR_VALUE}" == "1" || "${START_EXECUTOR_NORMALIZED}" == "yes" ]]; then
  python3 -m app.executor.service &
  EXECUTOR_PID=$!
fi

cleanup() {
  if [[ -n "${EXECUTOR_PID}" ]] && kill -0 "${EXECUTOR_PID}" >/dev/null 2>&1; then
    kill "${EXECUTOR_PID}" || true
  fi
}

trap cleanup EXIT INT TERM

exec uvicorn app.api.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}"
