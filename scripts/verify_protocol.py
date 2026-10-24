#!/usr/bin/env python3
"""Reproducible checks for the DUML assertions in docs/protocol-verification.md.

Pure stdlib, no DJI code bundled. Verifies the protocol structure from first
principles against a real captured DJI packet. The cross-checks against the
o-gs/dji-firmware-tools reference (enum values, dissector offsets) are described in
the doc; pass --reference /path/to/dji-firmware-tools to re-run those too.

Exit code is non-zero if any check fails.
"""
import argparse
import os
import struct
import sys

from _log import log

# A real captured DJI packet: PC -> Remote Controller, cmd_set 0x06 / cmd_id 0x01.
CAPTURED = bytes.fromhex("550d04330a06eb344006017424")


def crc8(seed, data):
    crc = seed
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8C if crc & 1 else crc >> 1
    return crc & 0xFF


def crc16(seed, data):
    crc = seed
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", help="path to a dji-firmware-tools clone for enum cross-checks")
    args = ap.parse_args()

    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    p = CAPTURED
    tag = p[1] | (p[2] << 8)
    check("header CRC-8 (poly 0x8C, seed 0x77) == byte[3]", crc8(0x77, p[:3]) == p[3], hex(p[3]))
    c16 = crc16(0x3692, p[:-2])
    check("packet CRC-16 (poly 0x8408, seed 0x3692) == tail", (c16 & 0xFF, c16 >> 8) == (p[-2], p[-1]), hex(c16))
    check("length field == actual length", (tag & 0x3FF) == len(p))
    check("version field == 1", ((tag >> 10) & 0x3F) == 1)
    check("SOF == 0x55", p[0] == 0x55)
    check("sender type == PC (10)", (p[4] & 0x1F) == 10)
    check("receiver type == REMOTE_RADIO (6)", (p[5] & 0x1F) == 6)
    check("cmd_set == RADIO (6), cmd_id == 1", (p[9], p[10]) == (6, 1))
    check("ack bits (5-6) == after-exec (2)", ((p[8] >> 5) & 3) == 2)

    # OSD General payload layout self-consistency: build a payload, read it back.
    lon_rad, lat_rad = 151.2093 * 3.141592653589793 / 180, -33.8688 * 3.141592653589793 / 180
    payload = struct.pack("<ddhhhhhhh", lon_rad, lat_rad, 1234, 15, -20, 5, 100, -45, 1800)
    vals = struct.unpack("<ddhhhhhhh", payload[:struct.calcsize("<ddhhhhhhh")])
    check("OSD layout lon@0/lat@8/relh@16/vel@18.. round-trips", vals[2] == 1234 and vals[-1] == 1800)
    check("OSD lon radians->deg ~= 151.2093", abs(vals[0] * 180 / 3.141592653589793 - 151.2093) < 1e-4)

    if args.reference:
        sys.path.insert(0, args.reference)
        try:
            from comm_mkdupc import COMM_DEV_TYPE as DT, CMD_SET_TYPE as CS
            check("[ref] device types match", (DT.MOBILE_APP.value, DT.FLYCONTROLLER.value,
                  DT.REMOTE_RADIO.value, DT.PC.value) == (2, 3, 6, 10))
            check("[ref] cmd sets match", (CS.GENERAL.value, CS.FLYCONTROLLER.value) == (0, 3))
        except Exception as e:  # noqa: BLE001
            check("[ref] import", False, str(e))

    width = max(len(n) for n, _, _ in checks)
    failed = 0
    for name, ok, detail in checks:
        log(f"{name:{width}}  {'PASS' if ok else 'FAIL'}  {detail}", "INFO" if ok else "ERROR")
        failed += not ok
    log(f"{len(checks)} checks, {failed} failed", "ERROR" if failed else "ALERT")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
