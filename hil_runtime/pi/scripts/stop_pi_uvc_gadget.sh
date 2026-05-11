#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"
STATE_DIR="${PI_GATEWAY_STATE_DIR:-${PROJECT_ROOT}/run_data/pi_gateway}"
STATE_FILE="${STATE_DIR}/gadget_state.json"
USB_NETWORK_INTERFACE="${PI_GATEWAY_USB_NETWORK_INTERFACE:-usb0}"
COMPOSITE_GADGET_NAME="${PI_GATEWAY_USB_GADGET_NAME:-duckpark}"
COMPOSITE_GADGET_ROOT="/sys/kernel/config/usb_gadget/${COMPOSITE_GADGET_NAME}"
UVC_FUNCTION_NAME="${PI_GATEWAY_USB_UVC_FUNCTION_NAME:-uvc.0}"
ECM_FUNCTION_NAME="${PI_GATEWAY_USB_ECM_FUNCTION_NAME:-ecm.usb0}"

if [[ -d "${COMPOSITE_GADGET_ROOT}" ]]; then
  sudo bash -lc "
    set -euo pipefail
    root='${COMPOSITE_GADGET_ROOT}'
    if [[ -w \"\${root}/UDC\" ]]; then
      printf '' > \"\${root}/UDC\" || true
    fi
    rm -f \"\${root}/configs/c.1/${UVC_FUNCTION_NAME}\" || true
    rm -f \"\${root}/configs/c.1/${ECM_FUNCTION_NAME}\" || true
    rm -f \"\${root}/functions/${UVC_FUNCTION_NAME}/control/class/fs/h\" || true
    rm -f \"\${root}/functions/${UVC_FUNCTION_NAME}/control/class/ss/h\" || true
    rm -f \"\${root}/functions/${UVC_FUNCTION_NAME}/streaming/class/fs/h\" || true
    rm -f \"\${root}/functions/${UVC_FUNCTION_NAME}/streaming/class/hs/h\" || true
    rm -f \"\${root}/functions/${UVC_FUNCTION_NAME}/streaming/class/ss/h\" || true
    rm -f \"\${root}/functions/${UVC_FUNCTION_NAME}/streaming/header/h/u\" || true
    find \"\${root}\" -depth -type d -exec rmdir {} + 2>/dev/null || true
  "
fi

sudo modprobe -r g_webcam >/dev/null 2>&1 || true
sudo modprobe -r g_ether usb_f_rndis usb_f_ecm usb_f_uvc u_ether >/dev/null 2>&1 || true
sudo ip addr flush dev "${USB_NETWORK_INTERFACE}" >/dev/null 2>&1 || true
rm -f "${STATE_FILE}"

echo "UVC gadget stopped"
