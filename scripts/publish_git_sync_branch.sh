#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(git -C "${PROJECT_ROOT}" rev-parse --show-toplevel)"

SOURCE_REF="${SOURCE_REF:-HEAD}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-rabbitank/carla-web-platform-sync}"
REMOTE_NAME="${REMOTE_NAME:-origin}"
SKIP_PUSH=0

usage() {
  cat <<'EOF'
Usage: bash scripts/publish_git_sync_branch.sh [options]

Options:
  --source-ref <ref>         Source commit/branch. Default: HEAD
  --deploy-branch <branch>   Subtree publish branch. Default: rabbitank/carla-web-platform-sync
  --remote <name>            Git remote. Default: origin
  --skip-push                Only compute subtree split commit
  -h, --help                 Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-ref)
      SOURCE_REF="$2"
      shift 2
      ;;
    --deploy-branch)
      DEPLOY_BRANCH="$2"
      shift 2
      ;;
    --remote)
      REMOTE_NAME="$2"
      shift 2
      ;;
    --skip-push)
      SKIP_PUSH=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '[publish-git-sync] unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

PROJECT_PREFIX="$(python3 - "${REPO_ROOT}" "${PROJECT_ROOT}" <<'PY'
from pathlib import Path
import sys

repo_root = Path(sys.argv[1]).resolve()
project_root = Path(sys.argv[2]).resolve()
print(project_root.relative_to(repo_root).as_posix())
PY
)"

SPLIT_COMMIT="$(git -C "${REPO_ROOT}" subtree split --prefix="${PROJECT_PREFIX}" "${SOURCE_REF}")"

if (( SKIP_PUSH == 0 )); then
  git -C "${REPO_ROOT}" push --force "${REMOTE_NAME}" "${SPLIT_COMMIT}:refs/heads/${DEPLOY_BRANCH}"
fi

printf 'repo_root=%s\n' "${REPO_ROOT}"
printf 'project_prefix=%s\n' "${PROJECT_PREFIX}"
printf 'source_ref=%s\n' "${SOURCE_REF}"
printf 'split_commit=%s\n' "${SPLIT_COMMIT}"
printf 'deploy_branch=%s\n' "${DEPLOY_BRANCH}"
printf 'remote=%s\n' "${REMOTE_NAME}"
