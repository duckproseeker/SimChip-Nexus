#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
HIL_RUNTIME_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
SRC_ROOT="${DUCKPARK_SRC_ROOT:-$(cd -- "${HIL_RUNTIME_ROOT}/.." && pwd)}"
PROJECT_ROOT="${DUCKPARK_PLATFORM_ROOT:-${SRC_ROOT}/carla_web_platform}"
source "${SCRIPT_DIR}/pi_gadget_common.sh"

STATE_DIR="${PI_GATEWAY_STATE_DIR:-${PROJECT_ROOT}/run_data/pi_gateway}"
STATE_FILE="${STATE_DIR}/gadget_state.json"
VENDOR_ID="${PI_GATEWAY_USB_VENDOR_ID:-0x1d6b}"
PRODUCT_ID="${PI_GATEWAY_USB_PRODUCT_ID:-0x0102}"
MANUFACTURER="${PI_GATEWAY_USB_MANUFACTURER:-DuckPark}"
PRODUCT_NAME="${PI_GATEWAY_USB_PRODUCT_NAME:-DuckPark UVC}"
SERIAL_NUMBER="${PI_GATEWAY_USB_SERIAL:-DUCKPARKPI5}"
GADGET_MODE="${PI_GATEWAY_USB_GADGET_MODE:-uvc_only}"
USB_NETWORK_CIDR="${PI_GATEWAY_USB_NETWORK_CIDR:-}"
USB_NETWORK_INTERFACE="${PI_GATEWAY_USB_NETWORK_INTERFACE:-usb0}"
USB_DEVICE_MAC="${PI_GATEWAY_USB_DEVICE_MAC:-02:1a:11:00:00:01}"
USB_HOST_MAC="${PI_GATEWAY_USB_HOST_MAC:-02:1a:11:00:00:02}"
COMPOSITE_GADGET_NAME="${PI_GATEWAY_USB_GADGET_NAME:-duckpark}"
COMPOSITE_GADGET_ROOT="/sys/kernel/config/usb_gadget/${COMPOSITE_GADGET_NAME}"
UVC_FUNCTION_NAME="${PI_GATEWAY_USB_UVC_FUNCTION_NAME:-uvc.0}"
ECM_FUNCTION_NAME="${PI_GATEWAY_USB_ECM_FUNCTION_NAME:-ecm.usb0}"

mkdir -p "${STATE_DIR}"
rm -f "${STATE_FILE}"

if [[ ! -d /sys/class/udc ]] || [[ -z "$(ls -A /sys/class/udc 2>/dev/null || true)" ]]; then
  cat >&2 <<'EOF'
未检测到 UDC。

请先确认树莓派 5 已启用 USB peripheral 模式：
  [pi5]
  dtoverlay=dwc2,dr_mode=peripheral

并且重启后 /sys/class/udc 下能看到控制器节点。
EOF
  exit 1
fi

ensure_configfs_mounted() {
  if mountpoint -q /sys/kernel/config; then
    return 0
  fi
  sudo mount -t configfs none /sys/kernel/config
}

remove_configfs_gadget() {
  if [[ ! -d "${COMPOSITE_GADGET_ROOT}" ]]; then
    return 0
  fi

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
}

write_uvc_frame_descriptor() {
  local frame_dir="$1"
  local width="$2"
  local height="$3"
  local fps_csv="$4"
  local default_fps="$5"

  local buffer_size=$((width * height * 2))
  local min_bitrate=$((width * height * 16 * default_fps))
  local intervals=""
  local fps
  IFS=',' read -ra fps_values <<<"${fps_csv}"
  for fps in "${fps_values[@]}"; do
    local normalized="${fps// /}"
    [[ -n "${normalized}" ]] || continue
    intervals+="$((10000000 / normalized))"$'\n'
  done

  sudo mkdir -p "${frame_dir}"
  printf '%s\n' "${width}" | sudo tee "${frame_dir}/wWidth" >/dev/null
  printf '%s\n' "${height}" | sudo tee "${frame_dir}/wHeight" >/dev/null
  printf '%s\n' "${min_bitrate}" | sudo tee "${frame_dir}/dwMinBitRate" >/dev/null
  printf '%s\n' "${min_bitrate}" | sudo tee "${frame_dir}/dwMaxBitRate" >/dev/null
  printf '%s\n' "${buffer_size}" | sudo tee "${frame_dir}/dwMaxVideoFrameBufferSize" >/dev/null
  printf '%s\n' "$((10000000 / default_fps))" | sudo tee "${frame_dir}/dwDefaultFrameInterval" >/dev/null
  printf '%s' "${intervals}" | sudo tee "${frame_dir}/dwFrameInterval" >/dev/null
}

configure_configfs_uvc_gadget() {
  local include_ecm="$1"
  local udc_name
  udc_name="$(ls /sys/class/udc | head -n1)"

  sudo modprobe -r g_webcam >/dev/null 2>&1 || true
  sudo modprobe -r g_ether usb_f_rndis >/dev/null 2>&1 || true
  sudo modprobe libcomposite
  sudo modprobe usb_f_uvc
  if [[ "${include_ecm}" == "true" ]]; then
    sudo modprobe usb_f_ecm
  fi

  ensure_configfs_mounted
  remove_configfs_gadget

  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}"
  printf '%s\n' "${VENDOR_ID}" | sudo tee "${COMPOSITE_GADGET_ROOT}/idVendor" >/dev/null
  printf '%s\n' "${PRODUCT_ID}" | sudo tee "${COMPOSITE_GADGET_ROOT}/idProduct" >/dev/null
  printf '0x0200\n' | sudo tee "${COMPOSITE_GADGET_ROOT}/bcdUSB" >/dev/null
  printf '0x0100\n' | sudo tee "${COMPOSITE_GADGET_ROOT}/bcdDevice" >/dev/null
  printf '0xEF\n' | sudo tee "${COMPOSITE_GADGET_ROOT}/bDeviceClass" >/dev/null
  printf '0x02\n' | sudo tee "${COMPOSITE_GADGET_ROOT}/bDeviceSubClass" >/dev/null
  printf '0x01\n' | sudo tee "${COMPOSITE_GADGET_ROOT}/bDeviceProtocol" >/dev/null

  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/strings/0x409"
  printf '%s\n' "${SERIAL_NUMBER}" | sudo tee "${COMPOSITE_GADGET_ROOT}/strings/0x409/serialnumber" >/dev/null
  printf '%s\n' "${MANUFACTURER}" | sudo tee "${COMPOSITE_GADGET_ROOT}/strings/0x409/manufacturer" >/dev/null
  printf '%s\n' "${PRODUCT_NAME}" | sudo tee "${COMPOSITE_GADGET_ROOT}/strings/0x409/product" >/dev/null

  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/configs/c.1/strings/0x409"
  printf '%s\n' "$([[ "${include_ecm}" == "true" ]] && printf '%s' 'DuckPark UVC + ECM' || printf '%s' 'DuckPark UVC')" | sudo tee "${COMPOSITE_GADGET_ROOT}/configs/c.1/strings/0x409/configuration" >/dev/null
  printf '250\n' | sudo tee "${COMPOSITE_GADGET_ROOT}/configs/c.1/MaxPower" >/dev/null

  if [[ "${include_ecm}" == "true" ]]; then
    sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/functions/${ECM_FUNCTION_NAME}"
    printf '%s\n' "${USB_DEVICE_MAC}" | sudo tee "${COMPOSITE_GADGET_ROOT}/functions/${ECM_FUNCTION_NAME}/dev_addr" >/dev/null
    printf '%s\n' "${USB_HOST_MAC}" | sudo tee "${COMPOSITE_GADGET_ROOT}/functions/${ECM_FUNCTION_NAME}/host_addr" >/dev/null
  fi

  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}"
  printf '1024\n' | sudo tee "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming_maxpacket" >/dev/null
  printf '1\n' | sudo tee "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming_interval" >/dev/null
  printf '1\n' | sudo tee "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming_maxburst" >/dev/null

  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/control/header/h"
  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/control/class/fs"
  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/control/class/ss"
  sudo ln -s \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/control/header/h" \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/control/class/fs/h"
  sudo ln -s \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/control/header/h" \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/control/class/ss/h"

  write_uvc_frame_descriptor \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/uncompressed/u/360p" \
    640 \
    360 \
    "30,15" \
    30
  write_uvc_frame_descriptor \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/uncompressed/u/480p" \
    640 \
    480 \
    "30,15" \
    30
  write_uvc_frame_descriptor \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/uncompressed/u/720p" \
    1280 \
    720 \
    "30,15" \
    30

  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/header/h"
  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/class/fs"
  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/class/hs"
  sudo mkdir -p "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/class/ss"
  sudo ln -s \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/uncompressed/u" \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/header/h/u"
  sudo ln -s \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/header/h" \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/class/fs/h"
  sudo ln -s \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/header/h" \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/class/hs/h"
  sudo ln -s \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/header/h" \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}/streaming/class/ss/h"

  if [[ "${include_ecm}" == "true" ]]; then
    sudo ln -s \
      "${COMPOSITE_GADGET_ROOT}/functions/${ECM_FUNCTION_NAME}" \
      "${COMPOSITE_GADGET_ROOT}/configs/c.1/${ECM_FUNCTION_NAME}"
  fi
  sudo ln -s \
    "${COMPOSITE_GADGET_ROOT}/functions/${UVC_FUNCTION_NAME}" \
    "${COMPOSITE_GADGET_ROOT}/configs/c.1/${UVC_FUNCTION_NAME}"

  printf '%s\n' "${udc_name}" | sudo tee "${COMPOSITE_GADGET_ROOT}/UDC" >/dev/null

  if [[ "${include_ecm}" == "true" && -n "${USB_NETWORK_CIDR}" ]]; then
    for _ in $(seq 1 20); do
      if ip link show "${USB_NETWORK_INTERFACE}" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done

    if ip link show "${USB_NETWORK_INTERFACE}" >/dev/null 2>&1; then
      sudo ip addr flush dev "${USB_NETWORK_INTERFACE}" >/dev/null 2>&1 || true
      sudo ip addr add "${USB_NETWORK_CIDR}" dev "${USB_NETWORK_INTERFACE}"
      sudo ip link set "${USB_NETWORK_INTERFACE}" up
    fi
  fi
}

configure_composite_gadget() {
  configure_configfs_uvc_gadget true
}

configure_configfs_uvc_only_gadget() {
  configure_configfs_uvc_gadget false
}

configure_legacy_g_webcam() {
  sudo modprobe -r g_webcam >/dev/null 2>&1 || true
  sudo modprobe -r g_ether usb_f_rndis u_ether >/dev/null 2>&1 || true
  remove_configfs_gadget
  sudo modprobe libcomposite
  sudo modprobe g_webcam \
    idVendor="${VENDOR_ID}" \
    idProduct="${PRODUCT_ID}" \
    iManufacturer="${MANUFACTURER}" \
    iProduct="${PRODUCT_NAME}" \
    iSerialNumber="${SERIAL_NUMBER}"
}

case "${GADGET_MODE}" in
  uvc_only)
    configure_legacy_g_webcam
    ;;
  configfs_uvc_only)
    configure_configfs_uvc_only_gadget
    ;;
  uvc_ecm)
    configure_composite_gadget
    ;;
  *)
    echo "未知 PI_GATEWAY_USB_GADGET_MODE: ${GADGET_MODE}" >&2
    exit 1
    ;;
esac

GADGET_DEVICE=""
for _ in $(seq 1 20); do
  GADGET_DEVICE="$(find_gadget_video_device || true)"
  if [[ -n "${GADGET_DEVICE}" ]]; then
    break
  fi
  sleep 1
done

if [[ -z "${GADGET_DEVICE}" ]]; then
  echo "UVC gadget 已加载，但未找到对应的 /dev/video 节点" >&2
  exit 1
fi

UDC_NAME="$(ls /sys/class/udc | head -n1)"
UDC_STATE="$(cat "/sys/class/udc/${UDC_NAME}/state" 2>/dev/null || echo unknown)"

cat > "${STATE_FILE}" <<EOF
{
  "started_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "gadget_driver": "$(
    if [[ "${GADGET_MODE}" == "uvc_ecm" ]]; then
      printf '%s' 'configfs_uvc_ecm'
    elif [[ "${GADGET_MODE}" == "configfs_uvc_only" ]]; then
      printf '%s' 'configfs_uvc'
    else
      printf '%s' 'g_webcam'
    fi
  )",
  "gadget_mode": "${GADGET_MODE}",
  "gadget_video_device": "${GADGET_DEVICE}",
  "udc_name": "${UDC_NAME}",
  "udc_state": "${UDC_STATE}",
  "usb_vendor_id": "${VENDOR_ID}",
  "usb_product_id": "${PRODUCT_ID}",
  "usb_network_interface": "${USB_NETWORK_INTERFACE}",
  "usb_network_cidr": "${USB_NETWORK_CIDR}"
}
EOF

echo "UVC gadget ready: ${GADGET_DEVICE} (UDC=${UDC_NAME}, state=${UDC_STATE})"
