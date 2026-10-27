# Mining an old chat, then closing it out

Procedure for a chat (pasted transcript, `chats/` record, old session) that may hold work not yet in the repo.
Goal: extract what is needed, prove where it landed, then the chat can be dropped.

## 1. Treat the chat as claims, not facts
- Chat statements are leads. Re-derive each from the repo or a re-run before it goes in a doc or issue.
- Any repo-state claim ("uncommitted edits", "branch lost", "not merged") is checked against live `git` first. A session-start `git status` snapshot goes stale within minutes.
- Mark each extracted item **V** (re-checked now) / **I** (inferred) / **U** (chat-only, unverified), per the verified/inferred convention in `CLAUDE.md`.

## 2. Triage every item into one bucket
| Bucket | Check | Action |
|---|---|---|
| Already in repo | `git branch -r --contains <sha>`; `git grep` for the symbol / number | note and drop |
| Code / script | `git log --all -S'<symbol>'` | commit to `scripts/` in this session, or delete |
| Measurement / finding | grep `docs/` for the number | add to the owning doc with conditions (what, when, capture); evidence goes in the issue |
| Open question / decision | search `gh issue list --search` first | issue, label `needs-dan`, comment on an existing one if same root cause |
| Dead end | not in repo | one line in the owning doc's open items, so it is not retried |
| Process lesson | recurs? | one bullet in this doc |

## 3. Close-out checklist
- Every item has a bucket and a location (commit SHA, doc path or issue number). No item is "in chat only".
- Dangling commits: `git branch -r --contains <sha>` must list `origin/main`; otherwise push a branch first.
- Redundant branches: delete only after `--contains` shows they are in `origin/main`. Remote deletes are outward-facing, so ask.
- Public repo (`awto-au/awto-dji`): issue and comment text is scrubbed (no `/mnt`, `/home`, secrets) and approved before posting. A write refused by the harness is drafted and handed over, never retried or worked around.
- Raw transcript, if kept, lives in `chats/YYYY-MM-DD-<topic>.md` with a header stating it is a reconstruction, not a verbatim export. Substance lives in `docs/`, not in the transcript.
- Last line of the close-out: list of what was filed, where, and what is still open.

## 4. Worked example: coordinator + SDR chat, 2026-10-26/27
Source: pasted transcript, truncated mid-sentence (ends in the Zenodo M100 static-channel constellation attempt). Items below were re-checked on 2026-10-27.

| Item from chat | Bucket | Result |
|---|---|---|
| Six "dangling" glassfalcon commits (`ea70d98`..`541daf5`) rescued to `rescue/glassfalcon-dangling-work` | Already in repo | **V** `541daf5` is in `origin/main`; `fw-check` registered in `dev.py`. Never at risk. |
| `origin/rescue/glassfalcon-dangling-work`, `origin/docs/glassfalcon-p3x-evaluation-20261026` | Redundant branches | **V** both contained in `origin/main`. Delete on Dan's say-so. |
| A session claimed uncommitted edits in the shared tree | Process lesson | Wrong: it used a stale session-start `git status`. Rule: section 1. |
| AoaMux replay: discard rate down from 32-42% to 12-14% (#64) | Measurement | **V** re-run `tool/replay_aoa_mux.dart` on `capture_local/aoa_relay_server-2026-10-26.log`: 13.6 / 12.4 / 12.7% on the three large segments (segment 2 is 1.9 kB, 78.7%, ignore). **Not yet on #64** (0 comments, open): chat's comment was refused. |
| #31 "fully resolved, close" | Issue state | **V** still OPEN. `541daf5` is on main. Close was refused in-chat; pending approval. |
| M100 OFDM numerology, pilots every 9 carriers (residues 5,5,8,8,2,2), `\|E r^4\|/E\|r\|^4` = 0.17 | Already in repo | **V** `docs/lightbridge-phy-measured.md`, `scripts/re/lightbridge_ofdm_params.py` (`pilot_search`, `constellation`). |
| Static-channel equalisation from all pilots gave coherence 0.007, worse than the 0.17 nearest-pilot reference | Dead end | **U** chat-only; the script on main still has the nearest-pilot version. Add one line to the open items in `docs/lightbridge-phy-measured.md` if retried. |
| Other session running on `analysis/lightbridge-cp-scan` | Process lesson | Shared checkout was switched under a session. Check `git branch --show-current` before any write; use a separate worktree for parallel work. |

## 5. Still to do from this example
- Comment the replay result on #64 (draft, awaiting approval).
- Close #31 with the `541daf5` evidence (draft, awaiting approval).
- Delete the two redundant remote branches (awaiting approval).
