# chats/

Chat records for mining (see `../docs/chat-mining.md`).

- Tracked: this file and `2026-10-26-lightbridge-wimax-iq-investigation.md` (a scrubbed reconstruction, cited by docs).
- Everything else here is local only and gitignored: raw session exports may hold secrets and private paths.
- Regenerate: `python3 -I scripts/chats_export.py` (reads `~/.claude/projects/<repo>/*.jsonl`, writes `chats/<start>-<session8>.md` plus `INDEX.tsv`; `--force` rewrites, `--thinking` includes reasoning blocks).
- Tool input/output is truncated (default 2000 chars). The full transcript stays in the source `.jsonl`.
- Mined and closed-out sessions live in `chats/archive/` (`--archive SID8...`). `INDEX.tsv` covers both folders.
