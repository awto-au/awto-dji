#!/usr/bin/env python3
"""Compare DUML cmdid coverage: APK-extracted facts (docs/data/apk-dynamic-cmdset-ids.tsv,
from the dynamically-unpacked DJI GO 4 dex - see docs/apk-analysis.md section 0 for the scope
this operates under) vs the public o-gs/dji-firmware-tools Wireshark dissector.

Finds: cmdids the APK has that the dissector doesn't decode (a real gap in the public tool),
and cmdids the dissector names that don't appear in the APK's enum (could be older/other-
product commands, or APK enum entries this script's regex missed - always spot-check before
treating as meaningful).

Usage: python3 -I scripts/re/compare_cmdset_gaps.py [--dji-tools-repo PATH]
Output: docs/data/cmdset-gap-report.tsv
Log: tmp/logs/compare_cmdset_gaps.log
"""
import argparse
import csv
import os
import re
import subprocess


def repo_root():
    return os.environ.get("AWTO_DJI_REPO") or subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))).strip()


ROOT = repo_root()

# cmdset_value -> (dissector file, lua table variable name, DJI_DUMLv1_CMD_SET_TEXT label)
CMDSET_TABLES = {
    0: ("dji-dumlv1-general.lua", "GENERAL_UART_CMD_TEXT", "General"),
    1: ("dji-dumlv1-proto.lua", "SPECIAL_UART_CMD_TEXT", "Special"),
    2: ("dji-dumlv1-camera.lua", "CAMERA_UART_CMD_TEXT", "Camera"),
    3: ("dji-dumlv1-flyc.lua", "FLYC_UART_CMD_TEXT", "Flight Control"),
    4: ("dji-dumlv1-gimbal.lua", "GIMBAL_UART_CMD_TEXT", "Gimbal"),
    5: ("dji-dumlv1-proto.lua", "CENTER_BRD_UART_CMD_TEXT", "Center Board"),
    6: ("dji-dumlv1-proto.lua", "RC_UART_CMD_TEXT", "Remote Control"),
    7: ("dji-dumlv1-proto.lua", "WIFI_UART_CMD_TEXT", "Wi-Fi"),
    8: ("dji-dumlv1-proto.lua", "DM36X_UART_CMD_TEXT", "DM36x"),
    9: ("dji-dumlv1-proto.lua", "HD_LINK_UART_CMD_TEXT", "HD Link"),
    10: ("dji-dumlv1-proto.lua", "MBINO_UART_CMD_TEXT", "Mono/Binocular"),
    11: ("dji-dumlv1-proto.lua", "SIM_UART_CMD_TEXT", "Simulator"),
    13: ("dji-dumlv1-proto.lua", "BATTERY_UART_CMD_TEXT", "Battery"),
    14: ("dji-dumlv1-proto.lua", "DATA_LOG_UART_CMD_TEXT", "Data Logger"),
    15: ("dji-dumlv1-proto.lua", "RTK_UART_CMD_TEXT", "RTK"),
    17: ("dji-dumlv1-proto.lua", "ADSB_UART_CMD_TEXT", "ADSB"),
}

ENTRY_RE = re.compile(r"^\s*\[(0x[0-9a-fA-F]+)\]\s*=\s*'([^']*)'")


def load_dissector_table(dissector_dir, filename, table_name):
    path = os.path.join(dissector_dir, filename)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    m = re.search(re.escape(table_name) + r"\s*=\s*\{(.*?)\n\}", text, re.DOTALL)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        em = ENTRY_RE.match(line)
        if em:
            out[int(em.group(1), 16)] = em.group(2)
    return out


SENTINEL_NAMES = {"Other", "ERROR"}  # catch-all enum defaults (value 511), not real commands


def load_apk_tsv(path):
    by_cmdset = {}
    with open(path) as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            if row["cmdid_name"] in SENTINEL_NAMES:
                continue
            cv = int(row["cmdset_value"])
            iv = int(row["cmdid_value"])
            by_cmdset.setdefault(cv, {})[iv] = row["cmdid_name"]
    return by_cmdset


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dji-tools-repo", default="/mnt/2tb/git/dji-firmware-tools")
    args = ap.parse_args()

    log_path = os.path.join(ROOT, "tmp", "logs", "compare_cmdset_gaps.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    lf = open(log_path, "w")

    def log(msg):
        print(msg)
        lf.write(msg + "\n")

    apk_tsv = os.path.join(ROOT, "docs", "data", "apk-dynamic-cmdset-ids.tsv")
    apk = load_apk_tsv(apk_tsv)
    dissector_dir = os.path.join(args.dji_tools_repo, "comm_dissector", "wireshark")

    out_path = os.path.join(ROOT, "docs", "data", "cmdset-gap-report.tsv")
    rows = []
    for cv, (filename, table_name, label) in sorted(CMDSET_TABLES.items()):
        dissector = load_dissector_table(dissector_dir, filename, table_name)
        apk_ids = apk.get(cv, {})
        log(f"cmdset {cv} ({label}): APK has {len(apk_ids)} ids, dissector has {len(dissector)}")
        apk_only = sorted(set(apk_ids) - set(dissector))
        dissector_only = sorted(set(dissector) - set(apk_ids))
        for iv in apk_only:
            rows.append((cv, label, iv, apk_ids[iv], "apk_only"))
        for iv in dissector_only:
            rows.append((cv, label, iv, dissector[iv], "dissector_only"))
        log(f"  apk_only={len(apk_only)} dissector_only={len(dissector_only)}")

    with open(out_path, "w") as out:
        out.write("cmdset_value\tcmdset_label\tcmdid_value\tname\tstatus\n")
        for cv, label, iv, name, status in rows:
            out.write(f"{cv}\t{label}\t{iv}\t{name}\t{status}\n")
    log(f"wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
