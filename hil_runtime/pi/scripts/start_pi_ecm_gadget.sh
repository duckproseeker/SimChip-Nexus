#!/usr/bin/env bash
set -euo pipefail

USB_NETWORK_CIDR="${PI_GATEWAY_USB_NETWORK_CIDR:-192.168.7.1/24}"
USB_NETWORK_INTERFACE="${PI_GATEWAY_USB_NETWORK_INTERFACE:-usb0}"
USB_DEVICE_MAC="${PI_GATEWAY_USB_DEVICE_MAC:-02:1a:11:00:00:01}"
USB_HOST_MAC="${PI_GATEWAY_USB_HOST_MAC:-02:1a:11:00:00:02}"
GADGET_NAME="${PI_GATEWAY_USB_GADGET_NAME:-duckpark}"
GADGET_ROOT="/sys/kernel/config/usb_gadget/${GADGET_NAME}"

log() {
  printf '%s pi-ecm-gadget %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

if [[ ! -d /sys/class/udc ]] || [[ -z "$(ls -A /sys/class/udc 2>/dev/null || true)" ]]; then
  echo "UDC not detected on Pi; peripheral mode is not enabled" >&2
  exit 1
fi

cleanup_configfs_gadget() {
  sudo bash -lc "
    set -euo pipefail
    root='${GADGET_ROOT}'
    if [[ ! -d \"\${root}\" ]]; then
      exit 0
    fi
    if [[ -w \"\${root}/UDC\" ]]; then
      printf '' > \"\${root}/UDC\" || true
    fi
    find \"\${root}\" -depth -mindepth 1 -exec rm -rf {} + 2>/dev/null || true
    rmdir \"\${root}\" 2>/dev/null || true
  "
}

log "switching Pi gadget to g_ether"
cleanup_configfs_gadget
sudo modprobe -r g_webcam g_ether usb_f_rndis usb_f_uvc usb_f_ecm u_ether libcomposite >/dev/null 2>&1 || true
sudo modprobe g_ether "dev_addr=${USB_DEVICE_MAC}" "host_addr=${USB_HOST_MAC}"

for _ in $(seq 1 20); do
  if ip link show "${USB_NETWORK_INTERFACE}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! ip link show "${USB_NETWORK_INTERFACE}" >/dev/null 2>&1; then
  echo "ECM interface did not appear: ${USB_NETWORK_INTERFACE}" >&2
  exit 1
fi

sudo ip addr flush dev "${USB_NETWORK_INTERFACE}" >/dev/null 2>&1 || true
sudo ip addr add "${USB_NETWORK_CIDR}" dev "${USB_NETWORK_INTERFACE}"
sudo ip link set "${USB_NETWORK_INTERFACE}" up

udc_name="$(ls /sys/class/udc | head -n1)"
udc_state="$(cat "/sys/class/udc/${udc_name}/state" 2>/dev/null || true)"

log "interface=${USB_NETWORK_INTERFACE} address=${USB_NETWORK_CIDR}"
ip -4 addr show "${USB_NETWORK_INTERFACE}"
log "udc=${udc_name} state=${udc_state:-unknown}"
