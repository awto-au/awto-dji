#!/usr/bin/env python3
"""Best-effort extraction of DUML command definitions from a decompiled DJI app's
dji/midware/data/model/*/Data*.java classes, into a comparable JSON table.

This is regex/text-pattern extraction over decompiled Java, NOT a real parser - it
works because this codebase's obfuscated-but-consistent field naming (the packet
builder object's cmdset/cmdid/sender/receiver fields are always literally named
m/n/f/h across every DJI app decompiled so far, 2026-10-24: dji.go.v4 and dji.pilot
both) turns out to be a stable, cross-app pattern worth relying on - verified by hand
against DataGimbalControl.java/DataGimbalAngleControl.java/
DataRcRequestGimbalCtrPermission.java before trusting it here. Confidence is tagged
per-record (V/I/U, see CLAUDE.md): V = cmdset+cmdid+at least one field offset all
matched cleanly; U = doPack()/field assignment pattern didn't match cleanly (raw
doPack() body is kept so a human can read it directly).

Usage:
    python3 -I scripts/re/extract_duml_classes.py <decompiled_source_root>... \
        --out tmp/apk/duml_tables/<name>.json

Multiple source roots merge into one table (e.g. dji.pilot's several carved-dex
trees); records are deduped by class name, first occurrence wins.
"""
import argparse
import json
import re
from pathlib import Path

CLASS_RE = re.compile(r"\bclass\s+(\w+)\b")
DOPACK_RE = re.compile(r"protected\s+void\s+doPack\(\)\s*\{(.*?)\n\s{4}\}", re.DOTALL)
# m/n/f/h are the packet-builder's cmdset/cmdid/sender/receiver fields - stable across
# every DJI app decompiled so far (see module docstring).
FIELD_ASSIGN_RE = re.compile(r"\.([mnhf])\s*=\s*([A-Za-z0-9_.]+)\.(?:a|b|value)\(\)\s*;")
# jadx sometimes casts the dest array ("(Object) this._sendData") and/or aliases it to
# a local ("byte[] bArr = this._sendData; bArr[6] = ...") depending on how a given dex
# was optimized - same bytecode, cosmetically different decompile. Confirmed
# 2026-10-24: this is exactly why DataGimbalAbsAngleControl's dji.go.v4 and dji.pilot
# decompiles looked different before normalize_aliases() below - same real command,
# same payload, jadx just wrote the array access differently. Don't skip this
# normalization - without it, "divergence" output is noise, not a real finding.
ALIAS_DECL_RE = re.compile(r"byte\[\]\s+(\w+)\s*=\s*this\._sendData\s*;")
ARRAYCOPY_RE = re.compile(
    r"System\.arraycopy\(([^;]*?),\s*0,\s*(?:\([\w\[\]]+\)\s*)?this\._sendData,\s*(\d+),\s*(\d+)\)")
BYTE_ASSIGN_RE = re.compile(r"this\._sendData\[(\d+)\]\s*=\s*([^;]+);")
# Third decompile style seen (DataCameraSetImageSize.java etc): the leading bytes are
# an array-literal initializer at the point of creation, not separate index
# assignments - `this._sendData = new byte[]{(byte) this.a.value(), 0};`. Same
# bytecode semantics as index-assigning each one; split the top-level comma list
# (brace/paren-aware, since elements can themselves contain calls like
# `this.a.value()`) and treat position i as offset i, length 1 (a multi-byte field
# written this way would be mis-split into 1-byte pieces - an accepted heuristic
# limit, not silently wrong: the field `name` just won't be resolved for it either).
ARRAY_LITERAL_RE = re.compile(r"this\._sendData\s*=\s*new\s+byte\[\]\s*\{(.*?)\}\s*;", re.DOTALL)
SRC_FIELD_RE = re.compile(r"this\.(\w+)\)")


def split_top_level(s: str) -> list:
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(s):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(s[start:i])
            start = i + 1
    parts.append(s[start:])
    return [p.strip() for p in parts if p.strip()]

ROLE_NAMES = {"m": "cmdset", "n": "cmdid", "f": "sender", "h": "receiver"}


def normalize_aliases(body: str) -> str:
    """Rewrite `byte[] bArr = this._sendData; bArr[6] = ...` to use this._sendData
    directly, so ARRAYCOPY_RE/BYTE_ASSIGN_RE see the same shape regardless of this
    jadx decompile quirk (see ARRAYCOPY_RE comment)."""
    for alias in set(ALIAS_DECL_RE.findall(body)):
        body = re.sub(rf"\b{re.escape(alias)}\b", "this._sendData", body)
    body = re.sub(r"this\._sendData\s*=\s*this\._sendData\s*;", "", body)
    return body


def extract_one(path: Path) -> dict | None:
    text = path.read_text(errors="replace")
    m = CLASS_RE.search(text)
    if not m:
        return None
    class_name = m.group(1)

    roles = {}
    for role_code, ref in FIELD_ASSIGN_RE.findall(text):
        roles[ROLE_NAMES[role_code]] = ref.split(".")[-1]

    dopack_match = DOPACK_RE.search(text)
    fields = []
    dopack_body = normalize_aliases(dopack_match.group(1)) if dopack_match else ""
    if dopack_match:
        for src, offset, length in ARRAYCOPY_RE.findall(dopack_body):
            name_m = SRC_FIELD_RE.search(src)
            fields.append({
                "offset": int(offset), "length": int(length),
                "name": name_m.group(1) if name_m else None,
            })
        for offset, _rhs in BYTE_ASSIGN_RE.findall(dopack_body):
            fields.append({"offset": int(offset), "length": 1, "name": None})
        literal_m = ARRAY_LITERAL_RE.search(dopack_body)
        if literal_m:
            for i, elem in enumerate(split_top_level(literal_m.group(1))):
                name_m = SRC_FIELD_RE.search(elem)
                fields.append({
                    "offset": i, "length": 1,
                    "name": name_m.group(1) if name_m else None,
                })

    confident = bool(roles.get("cmdset") and roles.get("cmdid") and fields)
    record = {
        "class": class_name,
        "cmdset": roles.get("cmdset"), "cmdid": roles.get("cmdid"),
        "sender": roles.get("sender"), "receiver": roles.get("receiver"),
        "fields": sorted(fields, key=lambda f: f["offset"]),
        "confidence": "V" if confident else "U",
    }
    if not confident:
        record["raw_dopack"] = dopack_body.strip() if dopack_match else None
        record["has_dopack"] = dopack_match is not None
    return record


def extract_tree(root: Path) -> dict:
    """-> {class_name: record}, searching dji/midware/data/model/*/Data*.java under root."""
    out = {}
    for path in root.glob("**/dji/midware/data/model/*/Data*.java"):
        record = extract_one(path)
        if record:
            out[record["class"]] = record
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+", type=Path, help="decompiled source root(s)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    merged: dict[str, dict] = {}
    for root in args.roots:
        found = extract_tree(root)
        for name, record in found.items():
            merged.setdefault(name, record)  # first occurrence wins across roots

    args.out.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(merged.values(), key=lambda r: r["class"])
    args.out.write_text(json.dumps(records, indent=2))
    n_v = sum(1 for r in records if r["confidence"] == "V")
    print(f"{len(records)} classes ({n_v} V, {len(records) - n_v} U) -> {args.out}")


if __name__ == "__main__":
    main()
