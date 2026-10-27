#!/usr/bin/env python3
"""Export Claude Code session transcripts (JSONL) to markdown in ./chats/ (gitignored).

Usage: python3 -I scripts/chats_export.py [--src DIR] [--out DIR] [--tool-max N] [--thinking] [--force] [--archive SID8...]
Default src: ~/.claude/projects/<repo path with / -> ->. Top-level sessions only (no subagent dirs).
Tool input/output is truncated to --tool-max chars; chats/ may hold secrets, never commit it.
Log: tmp/logs/chats_export.log
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def repo_root():
    # AWTO_DJI_REPO env -> git toplevel -> file-relative
    env = os.environ.get("AWTO_DJI_REPO")
    if env:
        return Path(env)
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
                             cwd=Path(__file__).resolve().parent).stdout.strip()
        return Path(top)
    except Exception:
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
LOG = ROOT / "tmp" / "logs" / "chats_export.log"
SKIP = ("<browser_instruction>", "<system-reminder>", "<local-command", "<command-")


def log(msg):
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}"
    print(line, file=sys.stderr)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def clip(text, n):
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    return text if len(text) <= n else text[:n] + f"\n... [truncated {len(text) - n} chars]"


def block_text(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def render(path, tool_max, thinking):
    out, first_user, t0, t1, n = [], None, None, None, 0
    for line in open(path, errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        ts = d.get("timestamp")
        if ts:
            t0, t1 = t0 or ts, ts
        m = d.get("message")
        if d.get("type") not in ("user", "assistant") or not isinstance(m, dict):
            continue
        n += 1
        who, c = d["type"], m.get("content")
        if isinstance(c, str):
            out.append(f"## {who} {ts or ''}\n\n{c}\n")
            if who == "user" and not first_user and not c.lstrip().startswith(SKIP):
                first_user = c
            continue
        parts = []
        for b in c or []:
            t = b.get("type")
            if t == "text":
                parts.append(b["text"])
            elif t == "thinking" and thinking:
                parts.append("> thinking: " + clip(b.get("thinking", ""), tool_max))
            elif t == "tool_use":
                parts.append(f"[tool_use] {b.get('name')} {clip(b.get('input', {}), tool_max)}")
            elif t == "tool_result":
                parts.append("[tool_result]\n```\n" + clip(block_text(b.get("content", "")), tool_max) + "\n```")
        if parts:
            out.append(f"## {who} {ts or ''}\n\n" + "\n\n".join(parts) + "\n")
            txt = block_text(c)
            if who == "user" and not first_user and txt and not txt.lstrip().startswith(SKIP):
                first_user = txt
    return out, first_user or "", t0, t1, n


def main():
    slug = str(ROOT).replace("/", "-")
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(Path.home() / ".claude" / "projects" / slug))
    ap.add_argument("--out", default=str(ROOT / "chats"))
    ap.add_argument("--tool-max", type=int, default=2000)
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--archive", nargs="+", metavar="SID8", help="move these exports to chats/archive/ (mined, closed out)")
    a = ap.parse_args()
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    arc = out_dir / "archive"
    for sid8 in a.archive or []:
        for f in out_dir.glob(f"*-{sid8}.md"):
            arc.mkdir(exist_ok=True)
            f.rename(arc / f.name)
            log(f"archived {f.name}")
    index = []
    for src in sorted(Path(a.src).glob("*.jsonl")):
        sid = src.stem
        existing = list(out_dir.glob(f"*-{sid[:8]}.md")) + list(arc.glob(f"*-{sid[:8]}.md"))
        if existing and not a.force and existing[0].stat().st_mtime >= src.stat().st_mtime:
            log(f"skip {sid[:8]} (up to date)")
            continue
        body, first, t0, t1, n = render(src, a.tool_max, a.thinking)
        start = (t0 or "unknown").replace("-", "").replace(":", "")[:15].replace("T", "-")
        dest = (existing[0].parent if existing else out_dir) / f"{start}-{sid[:8]}.md"
        for old in existing:
            old.unlink()
        title = " ".join(first.split())[:100]
        head = (f"# Session {sid}\n\n- start: {t0}\n- end: {t1}\n- messages: {n}\n- source: {src.name} "
                f"({src.stat().st_size} bytes)\n- first prompt: {title}\n"
                f"- tool input/output truncated to {a.tool_max} chars; thinking "
                f"{'included' if a.thinking else 'omitted'}\n- local only, gitignored, may contain secrets\n\n---\n\n")
        dest.write_text(head + "\n".join(body))
        index.append((dest.name, t0, t1, n, title))
        log(f"wrote {dest.name} msgs={n} bytes={dest.stat().st_size}")
    rows = []
    for md in sorted(list(out_dir.glob("*-????????.md")) + list(arc.glob("*-????????.md"))):
        h = {k: v for k, v in (l[2:].split(": ", 1) for l in md.read_text().split("---")[0].splitlines()
                               if l.startswith("- ") and ": " in l)}
        rows.append((("archive/" if md.parent == arc else "") + md.name, h.get("start"), h.get("end"), h.get("messages"), h.get("first prompt")))
    with open(out_dir / "INDEX.tsv", "w") as f:
        f.write("file\tstart\tend\tmessages\tfirst prompt\n")
        for row in rows:
            f.write("\t".join(str(x) for x in row) + "\n")


if __name__ == "__main__":
    main()
