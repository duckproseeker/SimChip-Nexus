#!/usr/bin/env bash
set -euo pipefail

gadget_video_name_matches() {
  local name="${1,,}"
  [[ "${name}" == *"gadget"* ]] || [[ "${name}" == *"uvc"* ]]
}

find_gadget_video_device() {
  local sysfs_device
  for sysfs_device in /sys/class/video4linux/video*; do
    [[ -e "${sysfs_device}" ]] || continue
    if [[ ! -r "${sysfs_device}/name" ]]; then
      continue
    fi
    local name
    name="$(tr -d '\0' < "${sysfs_device}/name" 2>/dev/null || true)"
    if [[ -z "${name}" ]]; then
      continue
    fi
    if gadget_video_name_matches "${name}"; then
      printf '/dev/%s\n' "${sysfs_device##*/}"
      return 0
    fi
  done

  python3 - <<'PY'
import subprocess

try:
    output = subprocess.run(
        ["v4l2-ctl", "--list-devices"],
        capture_output=True,
        check=False,
        text=True,
        timeout=2.0,
    ).stdout
except (FileNotFoundError, subprocess.TimeoutExpired):
    raise SystemExit(1)

current_block = None
for raw_line in output.splitlines():
    line = raw_line.rstrip()
    if not line:
        current_block = None
        continue
    if not raw_line.startswith("\t"):
        current_block = line.lower()
        continue
    if current_block and any(token in current_block for token in ("gadget", "uvc")):
        device = line.strip()
        if device.startswith("/dev/video"):
            print(device)
            break
PY
}
