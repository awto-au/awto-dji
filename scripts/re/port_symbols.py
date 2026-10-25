#!/usr/bin/env python3
"""String-anchored symbol port (part A): find anchor strings for upstream names in our image.

DJI functions log their own name (e.g. "call api_ctrl_mode_serial_open_nav_handler"), so an
upstream symbol name that appears as a substring of a string in our (different-revision) image
anchors that function: whatever references the string is almost always the named function.

This part parses an upstream IAR `.map` ("Publics by Value"), keeps DJI-style compound names, and
locates each as a substring of a C string in our decrypted module. It emits
    name <TAB> our_string_vaddr <TAB> full_string
for the Ghidra part (fc_port_names.py) to turn string_vaddr -> referencing function -> our address.

Usage: python3 scripts/re/port_symbols.py UPSTREAM.map OUR_m0306_dec.bin > anchors.tsv
"""
import re
import sys

MAP, BIN = sys.argv[1], sys.argv[2]
B = 0x08020000

# 1) upstream names from "Publics by Value"
names = set()
seen = False
for ln in open(MAP, encoding="utf-8", errors="replace"):
    if "Publics by Value" in ln:
        seen = True; continue
    if not seen:
        continue
    m = re.match(r"\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+(\S+)", ln)
    if m:
        names.add(m.group(1))

# keep DJI-style application names: compound identifiers, long enough to be distinctive.
STOP = {"destination", "memcpy", "memset", "memset_zero", "memcpy_0"}
def interesting(n):
    if n in STOP or n.startswith(("a", "__", "OS_", "OSCfg", "CPU_", "nullsub", "j_", "crc", "bit_")):
        # 'a'-prefixed are IAR string labels; keep names starting 'a' only if clearly a word boundary
        if not (n[0] == "a" and "_" in n and len(n) > 14):
            return False
    return n.count("_") >= 2 and len(n) >= 12 and re.match(r"^[A-Za-z][A-Za-z0-9_]*$", n)

cand = sorted(n for n in names if interesting(n))

# 2) all C strings in our image with their vaddr
img = open(BIN, "rb").read()
strings = []  # (vaddr, text)
i = 0
while i < len(img):
    j = i
    while j < len(img) and 32 <= img[j] < 127:
        j += 1
    if j - i >= 6 and j < len(img) and img[j] == 0:
        strings.append((B + i, img[i:j].decode()))
    i = j + 1

# 3) match each candidate name as a substring of some string (prefer the shortest string, i.e.
#    most specific anchor; and require the name be a token-bounded substring to avoid prefixes).
tok = re.compile(r"[A-Za-z0-9_]+")
def contains_name(s, n):
    # token-aware: n must appear with non-identifier boundaries (or string edge)
    idx = s.find(n)
    while idx != -1:
        before = s[idx - 1] if idx > 0 else " "
        after = s[idx + len(n)] if idx + len(n) < len(s) else " "
        if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
            return True
        idx = s.find(n, idx + 1)
    return False

print("name\tstring_vaddr\tstring")
hits = 0
for n in cand:
    best = None
    for va, s in strings:
        if n in s and contains_name(s, n):
            if best is None or len(s) < len(best[1]):
                best = (va, s)
    if best:
        hits += 1
        print("%s\t%#010x\t%s" % (n, best[0], best[1]))
sys.stderr.write("candidates=%d  anchored=%d\n" % (len(cand), hits))
