#!/usr/bin/env bash
set -euo pipefail

USB_NETWORK_INTERFACE="${PI_GATEWAY_USB_NETWORK_INTERFACE:-usb0}"

sudo ip link set "${USB_NETWORK_INTERFACE}" down >/dev/null 2>&1 || true
sudo ip addr flush dev "${USB_NETWORK_INTERFACE}" >/dev/null 2>&1 || true
sudo modprobe -r g_ether usb_f_rndis u_ether >/dev/null 2>&1 || true

printf '%s pi-ecm-gadget stopped interface=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${USB_NETWORK_INTERFACE}"
