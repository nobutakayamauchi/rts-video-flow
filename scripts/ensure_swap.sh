#!/usr/bin/env bash
set -euo pipefail

SWAP_FILE="${SWAP_FILE:-/swapfile}"
SWAP_SIZE="${SWAP_SIZE:-4G}"

if swapon --show=NAME --noheadings 2>/dev/null | awk '{$1=$1};1' | grep -Fxq "${SWAP_FILE}"; then
  echo "[ok] Swap already active: ${SWAP_FILE}"
  free -h
  exit 0
fi

if [[ ! -f "${SWAP_FILE}" ]]; then
  echo "[setup] Creating ${SWAP_SIZE} swap file at ${SWAP_FILE}"
  if ! sudo fallocate -l "${SWAP_SIZE}" "${SWAP_FILE}"; then
    echo "[warn] fallocate failed; using dd"
    sudo dd if=/dev/zero of="${SWAP_FILE}" bs=1M count=4096 status=progress
  fi
fi

sudo chmod 600 "${SWAP_FILE}"
sudo mkswap "${SWAP_FILE}" >/dev/null
sudo swapon "${SWAP_FILE}"

if ! grep -Eq "^${SWAP_FILE//\//\/}[[:space:]]" /etc/fstab; then
  echo "${SWAP_FILE} none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
fi

if ! swapon --show=NAME --noheadings 2>/dev/null | awk '{$1=$1};1' | grep -Fxq "${SWAP_FILE}"; then
  echo "[error] Swap activation failed" >&2
  exit 1
fi

echo "[ok] Swap active and persisted"
free -h
