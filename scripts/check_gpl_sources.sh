#!/usr/bin/env bash
# Checks whether DJI's published GPL source archives for the Phantom 3 (Ambarella
# platform) actually download. GPL v2 obliges DJI to *provide* the source, not merely
# list it, so this verifies the links resolve to real content.
#
# Observed 2026-10-21: busybox downloads fine; the Linux kernel link returns HTTP 200
# but zero bytes (effectively unavailable).
set -u

BASE="https://terra-1-g.djicdn.com/851d20f7b9f64838a34cd02351370894/Opensource"
declare -A URLS=(
  [linux-ambarella.tar.gz]="$BASE/linux-ambarella.tar.gz"
  [busybox-1.23.2.tar.bz2]="$BASE/busybox-1.23.2.tar.bz2"
)

rc=0
for name in "${!URLS[@]}"; do
  read -r code size < <(curl -sS --max-time 120 -o /dev/null \
    -w "%{http_code} %{size_download}" "${URLS[$name]}" 2>/dev/null || echo "000 0")
  if [[ "$code" == "200" && "$size" -gt 0 ]]; then
    printf 'OK    %-24s http=%s bytes=%s\n' "$name" "$code" "$size"
  else
    printf 'EMPTY %-24s http=%s bytes=%s  <-- source not actually downloadable\n' "$name" "$code" "$size"
    rc=1
  fi
done
exit $rc
