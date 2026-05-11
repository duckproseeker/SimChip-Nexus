#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=scripts/remote_ops_lib.sh
source "${PROJECT_ROOT}/scripts/remote_ops_lib.sh"

REMOTE_HOST_PROJECT_ROOT="${REMOTE_HOST_PROJECT_ROOT:-/home/du/ros2-humble/src/carla_web_platform}"
REMOTE_RUNTIME_PROJECT_ROOT="${REMOTE_RUNTIME_PROJECT_ROOT:-/ros2_ws/src/carla_web_platform}"
REMOTE_PROJECT_ROOT="${REMOTE_RUNTIME_PROJECT_ROOT}"
SYNC_SOURCE_REF="${SYNC_SOURCE_REF:-main}"
SYNC_BRANCH="${SYNC_BRANCH:-rabbitank/carla-web-platform-sync}"
SYNC_REMOTE="${SYNC_REMOTE:-origin}"
SYNC_REPO_URL="${SYNC_REPO_URL:-https://github.com/duckproseeker/duckPark.git}"
REMOTE_OWNER="${REMOTE_OWNER:-${REMOTE_USER}}"
REMOTE_NODE_IMAGE="${REMOTE_NODE_IMAGE:-node:20-bookworm-slim}"
LOCAL_FRONTEND_FALLBACK="${LOCAL_FRONTEND_FALLBACK:-1}"
SKIP_PUBLISH=0
SKIP_FRONTEND_BUILD=0
SKIP_RESTART=0
SKIP_SMOKE=0
LOCAL_DIST_ARCHIVE=""

usage() {
  cat <<'EOF'
Usage: bash scripts/remote_git_sync.sh <deploy|rollback> [options]

deploy:
  1. Publish src/carla_web_platform to a dedicated git sync branch
  2. Stop remote API / executor
  3. Fresh clone or fast-forward update on the host checkout
  4. Restore .env.local and persistent runtime directories
  5. Build frontend dist on the host with a Node 20 helper container
  6. Restart API / executor and run smoke

rollback:
  1. Stop remote API / executor
  2. Remove current checkout
  3. Restore the latest carla_web_platform_bak_<timestamp>
  4. Rebuild frontend dist, restart services, run smoke

Options:
  --source-ref <ref>             Source ref for subtree split. Default: main
  --sync-branch <branch>         Publish branch. Default: rabbitank/carla-web-platform-sync
  --sync-remote <name>           Git remote. Default: origin
  --repo-url <url>               Remote clone URL. Default: https://github.com/duckproseeker/duckPark.git
  --host-project-root <path>     Host checkout path. Default: /home/du/ros2-humble/src/carla_web_platform
  --runtime-project-root <path>  Container project path. Default: /ros2_ws/src/carla_web_platform
  --skip-publish                 Skip subtree branch publish
  --skip-frontend-build          Skip frontend dist build
  --skip-restart                 Skip service restart
  --skip-smoke                   Skip smoke
  -h, --help                     Show this help
EOF
}

publish_sync_branch() {
  bash "${PROJECT_ROOT}/scripts/publish_git_sync_branch.sh" \
    --source-ref "${SYNC_SOURCE_REF}" \
    --deploy-branch "${SYNC_BRANCH}" \
    --remote "${SYNC_REMOTE}"
}

deploy_remote_checkout() {
  local remote_script
  remote_script="$(cat <<EOF
set -euo pipefail

project_root=$(printf '%q' "${REMOTE_HOST_PROJECT_ROOT}")
project_parent=\$(dirname "\${project_root}")
repo_url=$(printf '%q' "${SYNC_REPO_URL}")
branch=$(printf '%q' "${SYNC_BRANCH}")
owner=$(printf '%q' "${REMOTE_OWNER}")
helper_container=$(printf '%q' "${REMOTE_CONTAINER}")
backup_marker=".git-sync-backup-path"
timestamp=\$(date +%Y%m%d_%H%M%S)
backup_path=""
latest_backup=""
failed_path=""
owner_uid=\$(id -u "\${owner}")
owner_gid=\$(id -g "\${owner}")
helper_image=\$(docker inspect --format '{{.Config.Image}}' "\${helper_container}" 2>/dev/null | head -n 1 || true)

if [[ -z "\${helper_image}" ]]; then
  helper_image="busybox:1.36"
fi

restore_persistent_dir() {
  local persistent_dir="\$1"
  local backup_entry="\${backup_path}/\${persistent_dir}"
  local project_entry="\${project_root}/\${persistent_dir}"

  if [[ ! -e "\${backup_entry}" ]]; then
    return 0
  fi

  rm -rf "\${project_entry}"
  if cp -a "\${backup_entry}" "\${project_entry}" 2>/dev/null; then
    chown -R "\${owner_uid}:\${owner_gid}" "\${project_entry}" || true
    return 0
  fi

  rm -rf "\${project_entry}"
  docker run --rm -v "\${project_parent}:\${project_parent}" "\${helper_image}" sh -lc \
    "cp -a \"\${backup_entry}\" \"\${project_entry}\" && chown -R \${owner_uid}:\${owner_gid} \"\${project_entry}\""
}

clone_checkout() {
  git clone --depth 1 --branch "\${branch}" "\${repo_url}" "\${project_root}"

  if [[ -n "\${backup_path}" ]]; then
    if [[ -f "\${backup_path}/.env.local" ]]; then
      cp -a "\${backup_path}/.env.local" "\${project_root}/.env.local"
    fi

    for persistent_dir in run_data artifacts; do
      restore_persistent_dir "\${persistent_dir}"
    done

    printf '%s\n' "\${backup_path}" > "\${project_root}/\${backup_marker}"
  fi
}

mkdir -p "\${project_parent}"
latest_backup=\$(find "\${project_parent}" -maxdepth 1 -type d -name "$(basename "${REMOTE_HOST_PROJECT_ROOT}")_bak_*" | sort | tail -n 1)

if [[ -d "\${project_root}/.git" ]]; then
  if [[ -f "\${project_root}/\${backup_marker}" ]]; then
    backup_path=\$(cat "\${project_root}/\${backup_marker}")
  elif [[ -n "\${latest_backup}" ]]; then
    backup_path="\${latest_backup}"
  fi

  git -C "\${project_root}" remote set-url origin "\${repo_url}"
  git -C "\${project_root}" fetch --depth 1 origin "\${branch}"
  git -C "\${project_root}" checkout -B "\${branch}" "origin/\${branch}"
  git -C "\${project_root}" reset --hard "origin/\${branch}"

  if [[ ! -f "\${project_root}/.env.local" && -n "\${backup_path}" && -f "\${backup_path}/.env.local" ]]; then
    cp -a "\${backup_path}/.env.local" "\${project_root}/.env.local"
  fi

  if [[ -n "\${backup_path}" ]]; then
    for persistent_dir in run_data artifacts; do
      if [[ ! -e "\${project_root}/\${persistent_dir}" || -L "\${project_root}/\${persistent_dir}" ]]; then
        restore_persistent_dir "\${persistent_dir}"
      fi
    done
  fi
else
  if [[ -e "\${project_root}" ]]; then
    backup_path="\${project_root}_bak_\${timestamp}"
    mv "\${project_root}" "\${backup_path}"
  fi
  clone_checkout
fi

for persistent_dir in run_data artifacts; do
  if [[ ! -e "\${project_root}/\${persistent_dir}" ]]; then
    mkdir -p "\${project_root}/\${persistent_dir}"
  fi
done

chown "\${owner}:\${owner}" "\${project_root}" || true
find "\${project_root}" -mindepth 1 -maxdepth 1 \
  ! -name run_data \
  ! -name artifacts \
  -exec chown -R "\${owner}:\${owner}" {} + || true
for persistent_dir in run_data artifacts; do
  if [[ -e "\${project_root}/\${persistent_dir}" ]]; then
    chown -R "\${owner}:\${owner}" "\${project_root}/\${persistent_dir}" || true
  fi
done

printf 'project_root=%s\n' "\${project_root}"
printf 'branch=%s\n' "\${branch}"
if [[ -n "\${backup_path}" ]]; then
  printf 'backup_path=%s\n' "\${backup_path}"
fi
if [[ -n "\${failed_path}" ]]; then
  printf 'failed_path=%s\n' "\${failed_path}"
fi
EOF
)"

  remote_host_bash "${remote_script}"
}

rollback_remote_checkout() {
  local remote_script
  remote_script="$(cat <<EOF
set -euo pipefail

project_root=$(printf '%q' "${REMOTE_HOST_PROJECT_ROOT}")
project_parent=\$(dirname "\${project_root}")
owner=$(printf '%q' "${REMOTE_OWNER}")
backup_marker=".git-sync-backup-path"
backup_path=""

if [[ -f "\${project_root}/\${backup_marker}" ]]; then
  backup_path=\$(cat "\${project_root}/\${backup_marker}")
fi

if [[ -z "\${backup_path}" ]]; then
  backup_path=\$(find "\${project_parent}" -maxdepth 1 -type d -name "$(basename "${REMOTE_HOST_PROJECT_ROOT}")_bak_*" | sort | tail -n 1)
fi

if [[ -z "\${backup_path}" || ! -d "\${backup_path}" ]]; then
  printf 'No backup checkout found for rollback\n' >&2
  exit 1
fi

rm -rf "\${project_root}"
mv "\${backup_path}" "\${project_root}"
chown -R "\${owner}:\${owner}" "\${project_root}"

printf 'project_root=%s\n' "\${project_root}"
printf 'restored_from=%s\n' "\${backup_path}"
EOF
)"

  remote_host_bash "${remote_script}"
}

build_remote_frontend() {
  local remote_script
  remote_script="$(cat <<EOF
set -euo pipefail

project_root=$(printf '%q' "${REMOTE_HOST_PROJECT_ROOT}")
node_image=$(printf '%q' "${REMOTE_NODE_IMAGE}")
owner=$(printf '%q' "${REMOTE_OWNER}")
owner_uid=\$(id -u "\${owner}")
owner_gid=\$(id -g "\${owner}")

rm -rf "\${project_root}/frontend/dist"
docker run --rm \
  -v "\${project_root}:\${project_root}" \
  -w "\${project_root}/frontend" \
  "\${node_image}" \
  bash -lc 'npm ci && npm run build'

chown -R "\${owner_uid}:\${owner_gid}" "\${project_root}/frontend/dist"
printf 'frontend_dist=%s\n' "\${project_root}/frontend/dist"
EOF
)"

  remote_host_bash "${remote_script}"
}

build_local_frontend() {
  (
    cd "${PROJECT_ROOT}/frontend"
    npm run build
  )
}

upload_local_frontend_dist() {
  local archive_name timestamp
  timestamp="$(date +%Y%m%d%H%M%S)"
  LOCAL_DIST_ARCHIVE="/tmp/duckpark_frontend_dist_${timestamp}.tgz"
  archive_name="$(basename "${LOCAL_DIST_ARCHIVE}")"

  COPYFILE_DISABLE=1 COPY_EXTENDED_ATTRIBUTES_DISABLE=1 \
    tar czf "${LOCAL_DIST_ARCHIVE}" --no-mac-metadata --no-xattrs -C "${PROJECT_ROOT}/frontend" dist
  remote_scp "${LOCAL_DIST_ARCHIVE}" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/${archive_name}"
  remote_host_bash "
set -euo pipefail
project_root=$(printf '%q' "${REMOTE_HOST_PROJECT_ROOT}")
owner=$(printf '%q' "${REMOTE_OWNER}")
mkdir -p \"\${project_root}/frontend\"
rm -rf \"\${project_root}/frontend/dist\"
tar xzf /tmp/${archive_name} -C \"\${project_root}/frontend\"
find \"\${project_root}/frontend/dist\" -name '._*' -delete || true
rm -f /tmp/${archive_name}
chown -R \"\${owner}:\${owner}\" \"\${project_root}/frontend/dist\"
"
  rm -f "${LOCAL_DIST_ARCHIVE}"
  LOCAL_DIST_ARCHIVE=""
}

restart_and_smoke() {
  if (( SKIP_FRONTEND_BUILD == 0 )); then
    if ! build_remote_frontend; then
      if [[ "${LOCAL_FRONTEND_FALLBACK}" == "1" || "${LOCAL_FRONTEND_FALLBACK}" == "true" ]]; then
        build_local_frontend
        upload_local_frontend_dist
      else
        return 1
      fi
    fi
  fi

  if (( SKIP_RESTART == 0 )); then
    restart_remote_services
  fi

  if (( SKIP_SMOKE == 0 )); then
    run_remote_smoke basic
  fi
}

COMMAND="${1:-}"
if [[ "${COMMAND}" == "-h" || "${COMMAND}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ -z "${COMMAND}" ]]; then
  usage >&2
  exit 1
fi
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-ref)
      SYNC_SOURCE_REF="$2"
      shift 2
      ;;
    --sync-branch)
      SYNC_BRANCH="$2"
      shift 2
      ;;
    --sync-remote)
      SYNC_REMOTE="$2"
      shift 2
      ;;
    --repo-url)
      SYNC_REPO_URL="$2"
      shift 2
      ;;
    --host-project-root)
      REMOTE_HOST_PROJECT_ROOT="$2"
      shift 2
      ;;
    --runtime-project-root)
      REMOTE_RUNTIME_PROJECT_ROOT="$2"
      REMOTE_PROJECT_ROOT="$2"
      shift 2
      ;;
    --skip-publish)
      SKIP_PUBLISH=1
      shift
      ;;
    --skip-frontend-build)
      SKIP_FRONTEND_BUILD=1
      shift
      ;;
    --skip-restart)
      SKIP_RESTART=1
      shift
      ;;
    --skip-smoke)
      SKIP_SMOKE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '[remote-git-sync] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

require_remote_ops_cmds
ensure_remote_password

case "${COMMAND}" in
  deploy)
    if (( SKIP_PUBLISH == 0 )); then
      publish_sync_branch
    fi
    stop_remote_services
    deploy_remote_checkout
    restart_and_smoke
    ;;
  rollback)
    stop_remote_services
    rollback_remote_checkout
    restart_and_smoke
    ;;
  *)
    printf '[remote-git-sync] unknown command: %s\n' "${COMMAND}" >&2
    usage >&2
    exit 1
    ;;
esac
