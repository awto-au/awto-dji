#!/usr/bin/env python3
"""Extract DUML cmdset/cmdid numeric facts from the dynamically-unpacked DJI GO 4 dex
(tmp/apk/dynamic/decompiled/, git-ignored - see docs/apk-analysis.md section 0 for the scope
decision this operates under: numeric facts only, never DJI's code/expression, nothing from
this script's *input* is ever committed).

Parses dji/midware/data/config/P3/CmdSet.java with regexes (not a real Java parser - this file
is machine-generated enum boilerplate, regex is enough) to pull:
  - top-level CmdSet enum: NAME(value, ...)
  - each nested CmdIdType enum: NAME(value, ...)
and writes one row per (cmdset, cmdid) pair.

Usage: python3 -I scripts/re/extract_apk_cmdset.py
Output: docs/data/apk-dynamic-cmdset-ids.tsv
Log: tmp/logs/extract_apk_cmdset.log
"""
import os
import re
import subprocess


def repo_root():
    return os.environ.get("AWTO_DJI_REPO") or subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))).strip()


ROOT = repo_root()
SRC = os.path.join(ROOT, "tmp", "apk", "dynamic", "decompiled", "sources",
                    "dji", "midware", "data", "config", "P3", "CmdSet.java")
OUT = os.path.join(ROOT, "docs", "data", "apk-dynamic-cmdset-ids.tsv")

# Top-level: NAME(value, new b() { ... }),  -- value is the cmdset number.
CMDSET_RE = re.compile(r'^\s{4}([A-Z_][A-Za-z_0-9]*)\((\d+),', re.MULTILINE)
# Nested: NAME(value[, ...]),  inside "public enum CmdIdType implements dji.midware.g.a {"
CMDID_BLOCK_RE = re.compile(
    r'public enum CmdIdType implements dji\.midware\.g\.a \{(.*?)\n\s{8}\}', re.DOTALL)
CMDID_ENTRY_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z_0-9]*)\((\d+)', re.MULTILINE)


def main():
    log_path = os.path.join(ROOT, "tmp", "logs", "extract_apk_cmdset.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    lf = open(log_path, "w")

    def log(msg):
        print(msg)
        lf.write(msg + "\n")

    with open(SRC, "r", encoding="utf-8") as f:
        text = f.read()

    cmdset_positions = [(m.group(1), int(m.group(2)), m.start()) for m in CMDSET_RE.finditer(text)]
    log(f"found {len(cmdset_positions)} top-level CmdSet entries")

    rows = []
    for i, (name, value, pos) in enumerate(cmdset_positions):
        end = cmdset_positions[i + 1][2] if i + 1 < len(cmdset_positions) else len(text)
        block = text[pos:end]
        m = CMDID_BLOCK_RE.search(block)
        if not m:
            log(f"  {name} ({value}): no CmdIdType block found")
            continue
        entries = CMDID_ENTRY_RE.findall(m.group(1))
        log(f"  {name} ({value}): {len(entries)} cmdid entries")
        for cmdid_name, cmdid_value in entries:
            rows.append((value, name, int(cmdid_value), cmdid_name))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as out:
        out.write("cmdset_value\tcmdset_name\tcmdid_value\tcmdid_name\n")
        for cv, cn, iv, iname in rows:
            out.write(f"{cv}\t{cn}\t{iv}\t{iname}\n")
    log(f"wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
