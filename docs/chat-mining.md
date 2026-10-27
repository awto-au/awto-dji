# Mining an old chat, then closing it out

Procedure for a chat (pasted transcript, `chats/` record, old session) that may hold work not yet in the repo.
Goal: extract what is needed, prove where it landed, then the chat can be dropped.

## 1. Treat the chat as claims, not facts
- Chat statements are leads. Re-derive each from the repo or a re-run before it goes in a doc or issue.
- Any repo-state claim ("uncommitted edits", "branch lost", "not merged") is checked against live `git` first. A session-start `git status` snapshot goes stale within minutes.
- Mark each extracted item **V** (re-checked now) / **I** (inferred) / **U** (chat-only, unverified), per the verified/inferred convention in `CLAUDE.md`.

## 1a. Enumerate first, then check every assertion
- Before triage, list every assertion in the chat as a numbered row: repo state ("committed", "fixed", "pushed"), findings, decisions, external facts, open items, unfiled ideas.
- No sampling: a chat's own "done" and "filed" claims are the ones most worth checking (`git log`, `gh issue view`, file exists).
- Each row ends with a verdict (V / I / U / wrong) and a location. A row without one is not mined yet.
- Include items the chat only implied or dropped (a plan the user approved but never executed).

## 1b. Merge into existing documentation, do not append beside it
- Search `docs/`, `HANDOVER.md`, `HISTORY.md`, open issues and recent comments for each item before writing.
- Already documented and identical: link, do not copy.
- Contradicts existing text: fix that text in place and state what is now true in one line. A stale "not resolved" / "needs X" left behind is a defect.
- New: add to the doc that owns the topic and add its row to `docs/README.md` only if it is a new file.
- Re-read everything this session has already posted (issue comments, docs) against the chat's newer facts. Correct or retract it the same way.
- Work that belongs to another repo goes there (its docs or its issues). Do not park it here.

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

## 5. Worked example 2: first Renode / handover chat, 2026-10-22/23
Source: pasted transcript from the first cloud + Selwyn sessions, truncated mid-step ("4. Dump the ca"). Re-checked 2026-10-27.

| Item from chat | Bucket | Result |
|---|---|---|
| Renode m0900 scaffold; RCC_CFGR tag fix to pass the clock-switch wait | Already in repo | **V** `renode/platforms/m0900.repl:43`, `renode/README.md`. |
| m0900 firmware from DJI's CDN, container and module SHA-256 match | Already in repo | **V** `docs/data-manifest.md`, `renode/README.md` step 1. |
| "Zero SPI transactions in 15 s, AD9363 bring-up gated by DUML/GPIO from another module" | Superseded claim | **V** wrong: `docs/phy-params.md` "Gate" section: gated by board-code straps (PA0/PC15/PC14), stalls on FPGA reg 0x8A. #2's title and body still carry the old claim; its last comment corrects it. |
| Another session's uncommitted `docs/rf-sdr-and-repair.md` edit | Already in repo | **V** committed (`1bcf181`). |
| `origin/ccr-31b4a6f2-8fofnf` remote delete failed (proxy) | Redundant branch | **V** 0 commits not in `origin/main`; `origin/backup/ccr-pre-sync-a28877b` also 0. Delete on Dan's say-so. |
| Run camera (A9SE, Linux userspace) ELFs with syscalls emulated: `qemu-arm -strace` first to list syscalls/ioctls, then Unicorn + a small Rust syscall shim; kernel boot is not feasible | Open idea, not recorded | **U** not in `docs/` (only MCU-side Unicorn/Renode appear). Needs the camera rootfs, which #35 is extracting. |

Lessons from this one:
- A chat's "blocked on X" and "finding" lines age badly. Check later docs before carrying a finding forward; here the headline finding was disproved within days.
- An issue body written from a chat keeps the chat's claim after the docs move on. Fix the title when a comment overturns it.

## 5a. Worked example 3: S9 usbmon kernel + AOA fixes + Pixel, 2026-10-26
Source: pasted transcript, truncated mid-sentence in an Intel WiMAX paste. Re-checked 2026-10-27.

| Assertion in chat | Verdict | Where / result |
|---|---|---|
| Session work committed: #64 fix, #67 fix, Mbps UI, tooling/docs | V | `b33166e`, `8df2ddc`, `53f20b8`, `e26f633` |
| Permission-wait timeout fix; envelope-leak "real bug, fixed" | V | `7385613` (60 s timeout; trims over-declared envelope length). The live-test doc still said "not resolved": **fixed in place** in `docs/aoa-live-test-2026-10-26.md`. |
| Own earlier comment on #64 ("unresolved possible leak") | wrong | Contradicts `7385613`. Correction drafted, not yet posted. |
| Zero-IDR evidence added to #26 | V | Comment present on #26. |
| S9 parked in `awtoau/awto-samsung-s9#1`, kept out of this repo | V | Issue open. Build repo `awto-samsung-s9-build` has `docs/building.md` + scripts, 1 commit (`c9e472e`). |
| heimdall 3 s `EndSession` timeout is an upstream bug to report | wrong | Chat's own test: patched build failed differently ("Failed to unpack received packet"). Hypothesis disproved, do not report it. |
| Merging `fix/video-decoder-lifecycle-67` "would delete 31,883 lines" | wrong | That is a diff against an old base; a merge dry-run conflicts in one file only. Branch is on hold (memory: video-decoder-on-hold). |
| S9 restored to a working state | U | Last known: stuck in Download Mode, original boot not restored; recovery path (Smart Switch) undecided. Only in #1. |
| Pixel 3 XL as ground controller: bootloader unlocked, adb over WiFi (not persistent after reboot), stock kernel lacks `CONFIG_USB_MON`, root via magiskboot | U | In no repo doc or issue. Related: #70. |
| Pixel BLE "more modern" than S9 | wrong | Both Bluetooth 5.0 class; premise dropped. |
| Intel WiMAX PHY diagnostic interfaces | V | Already in `chats/2026-10-26-...md` and `docs/lightbridge-wimax-history.md`. |
| DJI Pilot aircraft-dropdown swipe unsolved | V | `docs/phone-bridge-operator-guide.md` "Known unreliable"; the raw `sendevent` variants tried are not recorded. |

Lessons:
- A fix landing makes the docs and issue comments written before it wrong. Re-read what you posted.
- A hypothesis a chat disproved itself must not be filed upstream.

## 6. Still to do
- #64: correct the 2026-10-27 status comment (leak was a real bug, fixed in `7385613`).
- #67: post the on-hold note.
- Pixel 3 XL ground-controller plan: no home yet; propose a comment on #70 or a new issue.
- S9 recovery: decide Smart Switch vs other; track on `awtoau/awto-samsung-s9#1`.
- Hardware re-test of `7385613` (permission timeout, envelope trim).
- Unmerged branches kept on purpose: `fix/video-decoder-lifecycle-67` (on hold), `claude/firmware-loading-trace-cbzvam` (8 conflicting docs).
