#!/usr/bin/env python3
"""Which human-readable messages in a firmware binary are NOT in a reference source tree?

Used to separate vendor (DJI) additions from unmodified reference code (TI DVSDK, mainline
Linux, U-Boot) in docs/m0800-dm368-provenance.md. String-level evidence only: a message found
in the reference means that code is present, not that the surrounding code is byte-identical.

Method: index every C string literal under the reference roots (adjacent and backslash-continued
literals joined, \\" \\t \\n unescaped). For each `strings -n 12` message in the binary that has
a space and a 4-letter word, drop log prefixes ("<3>", "FOO Error: ", "%s: "), split on printf
specs, newlines, ": " and "=>", and look up the longest remaining run (>= 10 chars).

Usage:  python3 scripts/re/ref_string_diff.py BINARY REF_ROOT [REF_ROOT ...]
Prints "# <name>: N messages, F in reference, M not" then the M unmatched messages.
"""
import os
import re
import subprocess
import sys

LIT = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
META = re.compile(r'GCC: \(|^Linux version|^(vermagic|author|description|license|alias|depends|srcversion)='
                  r'|built on |^\s*(<\d>)?\s*File /')


def literals(roots):
    parts = []
    for d in roots:
        for root, _, files in os.walk(d):
            for f in files:
                if not f.endswith((".c", ".h", ".S")):
                    continue
                with open(os.path.join(root, f), errors="replace") as fh:
                    t = fh.read()
                t = re.sub(r'"\s*\\?\s*\n\s*"', "", t)
                t = re.sub(r'"\s+"', "", t)
                parts.extend(m.group(1) for m in LIT.finditer(t))
    return "\x00".join(parts).replace('\\"', '"').replace("\\t", "\t").replace("\\n", "\n")


def main():
    binary, roots = sys.argv[1], sys.argv[2:]
    blob = literals(roots)
    out = subprocess.run(["strings", "-n", "12", binary], capture_output=True, text=True).stdout
    msgs = [s for s in out.splitlines() if " " in s.strip() and re.search("[a-zA-Z]{4}", s)
            and not s.startswith(("parm", "--cpu")) and not META.search(s)]
    miss = []
    for s in msgs:
        s0 = re.sub(r"^(<\d>)?\s*[A-Za-z0-9_.-]+( (Error|Warning|Debug|error|warning))?: (%s: )?", "", s)
        runs = [r.strip() for r in re.split(r"%[-+ #0-9.lhz]*[a-zA-Z]|<\d>|[\n\t]|: |=>", s0)]
        key = max(runs, key=len)
        if len(key) >= 10 and key not in blob:
            miss.append(s)
    print(f"# {os.path.basename(binary)}: {len(msgs)} messages, {len(msgs) - len(miss)} in reference, {len(miss)} not")
    for s in miss:
        print("   ", s)


if __name__ == "__main__":
    main()
