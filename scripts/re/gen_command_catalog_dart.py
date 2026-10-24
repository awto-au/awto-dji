#!/usr/bin/env python3
"""Generate app/awto_dji_app/lib/debug/command_catalog.dart from
docs/data/apk-dynamic-cmdset-ids.tsv (the canonical source - see docs/apk-analysis.md section 0
for where these facts come from). Regenerable build artifact, not a hand-copied duplicate.

Emits every command; `isGet` marks the Get* queries. Re-run this after any change to the TSV.

Usage: python3 -I scripts/re/gen_command_catalog_dart.py
"""
import csv
import os
import subprocess


def repo_root():
    return os.environ.get("AWTO_DJI_REPO") or subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))).strip()


SENTINEL_NAMES = {"Other", "ERROR"}


def main():
    root = repo_root()
    tsv_path = os.path.join(root, "docs", "data", "apk-dynamic-cmdset-ids.tsv")
    out_path = os.path.join(root, "app", "awto_dji_app", "lib", "debug", "command_catalog.dart")

    seen = set()
    rows = []
    with open(tsv_path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            name = row["cmdid_name"]
            if name in SENTINEL_NAMES:
                continue
            cv, iv = int(row["cmdset_value"]), int(row["cmdid_value"])
            key = (cv, iv)
            if key in seen:
                continue
            seen.add(key)
            rows.append((cv, row["cmdset_name"], iv, name))
    rows.sort()

    lines = [
        "// GENERATED - do not edit by hand.",
        "// Source: docs/data/apk-dynamic-cmdset-ids.tsv",
        "// Regenerate: python3 -I scripts/re/gen_command_catalog_dart.py",
        "library;",
        "",
        "class CatalogCommand {",
        "  const CatalogCommand(this.cmdSet, this.cmdSetName, this.cmdId, this.name);",
        "  final int cmdSet;",
        "  final String cmdSetName;",
        "  final int cmdId;",
        "  final String name;",
        "",
        "  /// Query commands (Get*); the rest set state or trigger actions.",
        "  bool get isGet => name.startsWith('Get');",
        "}",
        "",
        f"/// {len(rows)} commands, from the dynamically-unpacked DJI GO 4 enum.",
        "const List<CatalogCommand> kCommandCatalog = [",
    ]
    for cv, cn, iv, name in rows:
        esc = name.replace("'", "\\'")
        lines.append(f"  CatalogCommand({cv}, '{cn}', {iv}, '{esc}'),")
    lines.append("];")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {len(rows)} commands to {out_path}")


if __name__ == "__main__":
    main()
