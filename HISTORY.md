# History — 2026-10-26 session notes

Detailed record of a long live-hardware debugging session on 2026-10-26 (machine: Selwyn,
test phone: Samsung S9 "starlte" running LineageOS, test rig: a DJI Phantom 3 Professional
RC + aircraft). Unlike `HANDOVER.md` (kept terse, pick-up-and-go) and the other operational
docs, this file is allowed to be long: it exists so a future session doesn't have to re-derive
what happened here from the chat transcript. Read `HANDOVER.md` first for current state and
next steps; come here only when you need the detail behind a decision or a bug fix.

## Status at end of session

Most of the work described below is **uncommitted** in the working tree as of session end
(`git status --short` showed it still pending). Before relying on any of it, check it actually
landed — `git log` and `git status` are the source of truth, not this file.

## The AoaMux bare-frame discard bug (awto-dji#64) — the big one

**Starting point.** The app's `AoaMux` (`app/awto_dji_app/lib/transport/aoa_mux.dart`) and its
Python mirror (`scripts/re/aoa_mux.py`) parse the accessory command-channel byte stream as a
sequence of `55 cc <channel u16> <length u32> <payload>` envelopes. Every byte that doesn't fit
this model gets silently discarded. Live captures showed a suspiciously high discard rate, and
the session's job was to find out why.

**New ground-truth mechanism built to investigate it.** The existing TCP debug relay
(`app/awto_dji_app/lib/debug/tcp_relay.dart` + `scripts/re/aoa_relay_server.py`) only ever
forwarded AoaMux's *own* post-processed output (`ENVELOPE`/`DISCARDED` records) — useless for
checking whether AoaMux's own parsing is correct, since you're trusting the thing you're trying
to verify. Added a second, independent channel: `app/awto_dji_app/lib/debug/udp_raw_relay.dart`
sends every raw accessory byte chunk, verbatim, as its own UDP datagram (to the TCP relay port
+1) *before* AoaMux ever touches it, with an 8-byte header (seq u32 LE, CRC32 u32 LE) that is
entirely independent of anything DUML- or envelope-derived. `aoa_relay_server.py` runs a UDP
listener on that port, verifies the CRC32 and sequence continuity (so transport corruption and
real DUML corruption can never be confused with each other), and feeds the payloads through a
second, separately-stateful `StreamDemuxer`/`AoaMux` instance, logging to
`captures/sessions/<date>/aoa_relay_frames_raw.log`. This superseded an earlier, abandoned
design that tried to do the same thing by adding a `RAW` kind to the existing length-prefixed
TCP relay record format (commit `5cd5aa4` has the full before/after) — UDP was chosen instead
specifically because it preserves datagram boundaries natively, with no length-prefix parsing
that could itself be the thing with a bug, and incidentally makes the stream trivially sniffable
with any plain UDP capture tool. Whichever reason you reach for it, `UdpRawRelay`/the raw UDP
listener now *is* the project's ground-truth mechanism for anything touching AoaMux — use it
first before adding new diagnosis tooling.

**Root cause, established with two independent statistical checks (not guesswork):**
1. Rebuilt the complete accessory byte stream from the raw UDP capture, segmented by actual TCP
   connection boundaries (a subtlety that bit the investigation once — `UdpRawRelay`'s sequence
   counter resets to 0 on every reconnect, so naively concatenating by sequence number across
   reconnects silently corrupts the reconstruction and produces phantom "giant discard" findings
   that are purely an artifact of the reconstruction, not the real protocol — see
   `scripts/re/analyze_raw_capture.py`'s own docstring/`load_segments`, which exists specifically
   to not repeat that mistake).
2. Fed the reconstructed stream through `AoaMux` as a single buffer (no chunk boundaries
   possible at all) — still discarded 32–42% of bytes across capture segments. This ruled out
   "it's a chunk-boundary/read-fragmentation bug" as the explanation; the model is wrong even
   with zero fragmentation.
3. Of the discarded bytes, 43.4% turned out to be valid, CRC8-header + CRC16-frame DUML frames
   with **no envelope wrapper at all** (3,883 frames recovered in one capture, overwhelmingly
   sender `0x0e`/OSD). The odds of that many accidental CRC8+CRC16 passes on random bytes are
   about 1-in-16.7M per candidate position — over ~270KB of discarded bytes, pure chance
   predicts approximately zero hits, not thousands. So these are real frames.
4. Walked all sender-`0x0e` frames (both enveloped and bare) in true stream order and checked
   consecutive DUML sequence-number deltas: 53% are exactly `+1`, including transitions that
   cross from an enveloped frame straight into a bare one. A random 16-bit value matching
   "previous + 1" by chance is a 1-in-65,536 shot — getting that on over half of thousands of
   transitions is only possible if the enveloped and bare frames are genuinely one continuous
   logical sequence from the RC, just inconsistently wrapped. (The non-monotonic 47% looks like
   ordinary retransmission — exact duplicate sequence numbers reappearing a frame or two later —
   not noise.)
5. Checked and ruled out several more mundane explanations before accepting the above: the
   `55 cc` header's length field being misread as u32 instead of u16+reserved (checked against a
   third-party DJI USB-protocol RE doc, `samuelsadok/dji_protocol`'s `usb_mobile_protocol.md` —
   that repo documents the *same* envelope format with a u16 length + a separate "always 0x0000"
   field; verified against all 5,547 successfully-parsed envelopes in this project's own capture
   that bytes 6–7 are indeed always `0x0000`, so the u32-vs-u16 distinction is numerically
   harmless here, not the bug); whether bare-vs-enveloped correlates with sender/receiver/
   cmdset/cmdid (it doesn't — every single message-type combination observed is a *mix* of bare
   and enveloped, from 1% to 69% bare, so it's not "this message type is always bare"); whether
   bare frames are simple continuations sitting exactly where the previous envelope's declared
   length ran out (only 11.6% do — ruled out as the primary mechanism).

**Conclusion filed in #64, with the fix still open:** `AoaMux` needs to fall back to scanning for
a bare, CRC-valid DUML frame whenever envelope-matching fails at the current position, instead
of discarding. Not yet implemented in `app/awto_dji_app/lib/transport/aoa_mux.dart` or
`scripts/re/aoa_mux.py` — this is the next concrete code task.

**A second, independent, real bug was also found and fixed along the way (not the above fix —
a different thing found while chasing it):** `app/awto_dji_app/android/app/src/main/kotlin/au/
awto/dji/awto_dji_app/AoaShim.kt`'s `closeAccessory()` used to just set `reader = null` on
teardown, without ever calling `interrupt()` or `join()` on the old reader thread. Closing a
`ParcelFileDescriptor` is not guaranteed to unblock a thread already inside a blocking
`FileInputStream.read()` call on that fd (a known Android/Linux quirk, unlike e.g.
`Socket.close()`). If it doesn't, the old thread keeps running forever, still reading the same
underlying accessory character device, with its `generation` now stale — so the EventChannel
`sink` guard (`if (generation == readerGeneration)`) silently drops anything it *does* receive,
while it keeps competing with whatever reader opens next for the RC's real incoming bytes (and
on a character device, multiple blocked readers get an unpredictable, non-deterministic split of
whichever chunk arrives next — so a zombie reader can "steal" real data that never reaches the
live one). Fixed: `closeAccessory()` now explicitly closes `input` (the stream, not just the
`ParcelFileDescriptor` wrapper — closing the stream is the more reliable way to interrupt an
in-flight blocking read on this driver) and then joins the old reader thread with a 200ms bound
(20x margin over the low-single-digit-ms return time of a genuinely-unblocked thread), logging a
warning if it's still alive past that — so a zombie thread is visible in logcat instead of
invisible forever. This is a real, legitimate fix, independent of #64's envelope-model bug, and
worth keeping regardless of what else is found — but it does **not** fully explain the session's
remaining open mystery below, since that reproduced on a completely fresh process's very first
`open()` call, where no zombie thread could possibly have existed yet.

## Still open and unresolved at end of session: intermittent total silence from the RC

Separately from #64's bare-frame bug, a more basic problem kept recurring throughout the
session: long stretches where the phone received **zero bytes at all** from the accessory —
not corrupted/discarded data, nothing — despite the RC being confirmed physically powered on,
the phone's USB gadget being configured and active (not suspended), and TX (phone→RC writes)
continuing to succeed with no errors the whole time.

What was ruled out, in order:
- **The RC being off.** Confirmed on physically twice.
- **A simple USB power-management suspend.** `dwc3` state was `configured`, UDC `active`.
- **Kernel ftrace as a diagnostic tool on this phone's kernel build.** Repeatedly produced
  false "it's armed" confirmations that turned out to be silent failures (once because
  `debugfs`/`tracefs` doesn't survive a reboot and needs remounting — `mount -t debugfs none
  /sys/kernel/debug && mount -t tracefs none /sys/kernel/debug/tracing` — and even after fixing
  that and genuinely confirming `tracing_on=1` and the event `enable=1`, `dwc3_complete_trb`
  still never fired for confirmed real TX traffic). This Samsung/Exynos SoC (`10c00000.dwc3`,
  kernel `4.9.337-ies-20316`, a custom/non-stock build) most likely uses a vendor-wrapped dwc3
  driver whose real transfer-completion path bypasses the generic tracepoints; no alternative
  Exynos-specific USB trace event group exists (`ls events/` only shows generic `dwc3` and the
  unrelated `exynos_dpu` display group). **Kernel-level ftrace is not a usable diagnostic
  approach on this phone for this problem** — don't spend more time on it without a different
  angle (e.g. a genuinely different trace backend, or accepting app/relay-level logging as the
  ceiling of visibility here).
- **The zombie-reader-thread bug above**, for the specific case of a single connection's first
  ever `open()` call in a fresh process (no prior reader could exist to be a zombie). The fix
  is still worth keeping for cases where it *does* apply (the app's own `LinkHost.dart` has an
  automatic reconnect-on-failure loop, `_scheduleReconnect`, that would exercise exactly this
  path if the accessory stream ever genuinely errors/EOFs — just confirmed via logcat that in
  the specific sessions tested, `LinkState` stayed `connected` throughout and never actually
  errored, so that automatic-reconnect path, and therefore this specific fix, was never actually
  exercised in the sessions where the symptom was observed).

**One real, suggestive data point, not yet confirmed as a pattern:** after a full phone reboot
(not just an app restart — `adb reboot`, waited for `sys.boot_completed=1`), the very first
reconnect produced one genuine burst of real RC data (a 270-byte DUML envelope, decoded cleanly,
content matched the phone's own "Received: 262 B" telemetry readout exactly) glued to 16,114
bytes of literal zero-padding in the same 16,384-byte USB read (almost certainly backlog
draining from however long the link had been stuck). Every connection attempt *after* that one
burst, across several more reconnects in the same post-reboot session, got nothing again. This
pattern — full reboot unsticks it exactly once, then it sticks again — is consistent with
something stateful below the app, likely in the kernel/USB-gadget driver, that only a full
reboot clears. It has not been confirmed as reproducible (only observed once), and the
mechanism is not understood. **This is the single most important open question left by the
session.** Next step if picked back up: deliberately reproduce the "reboot → one burst → stuck
again" cycle at least once more to confirm it's real and not coincidence, ideally while also
capturing whatever `dmesg`/kernel log state is available (even without working ftrace) right
around the moment it gets stuck.

## DJI reference apps on the test phone

`dji.go.v4` ("DJI GO 4") **does not connect to a Phantom 3 Professional** — confirmed live: its
own UI, on selecting this aircraft, redirects to "DJI Pilot"/the classic "DJI GO" app, because
P3 isn't a supported aircraft in GO 4 itself (DJI GO 4 targets newer aircraft; P3/Inspire 1 are
the legacy "DJI GO"/DJI Pilot generation). This was already correctly documented in
`sources/README.md` as background from earlier decompiled-APK analysis, but hadn't been acted on
for the live test phone's actual app selection until this session. `dji.go.v4` has been
**uninstalled from the test phone entirely**. `dji.pilot` (already installed) is the correct
live reference app for this specific P3 Pro rig going forward — see
`docs/phone-bridge-operator-guide.md`'s "Test phone" section. A live connect test with
`dji.pilot` was in progress at end of session (aircraft selector had to be switched from its
cached "Inspire 1 RAW" default to Phantom 3 — not yet confirmed whether it successfully receives
RC data where the custom app didn't).

Note: `dji.go.v4`'s *decompiled APK code* remains a legitimate and still-used protocol-RE source
elsewhere in this repo's docs (DUML field layouts, command names, cmdset tables, etc.) — that
usage is unrelated to "does it connect live to our test rig" and was deliberately left untouched
throughout this session's doc cleanup.

## New reusable scripts (all under `scripts/re/`, wired into `./dev.py`)

- **`keepalive.py`** (`./dev.py keepalive`) — PC-side-only periodic `Get*` sends through the
  relay's command FIFO, built in response to #65's idle-timeout hypothesis. Two tiers: a fast
  one (`GetPushLinkMode`, default every 1s — chosen specifically because it's *not* already
  part of the RC's own automatic push stream, so sending it is a genuine inbound round-trip
  rather than a wasted duplicate of free telemetry) and a slow one (`GetFPGA`, `Get9363`,
  `GetVersion`, `GetPushBasebandState`, default every 60s — static-ish diagnostics, no reason to
  poll them fast). Deliberately implemented in Python rather than Dart specifically so tuning the
  keepalive strategy never needs an app rebuild+reinstall cycle.
- **`phone_bench.py`** (`./dev.py phone <sub>`) — reusable replacement for the ad-hoc adb
  one-liners that had been accumulating in this session. Subcommands: `connect` (force-stop,
  send the CONNECT intent, wait for the relay TCP connection and optionally N raw UDP reads),
  `stop`, `usb-state` (gadget state/recent USB events/foreground window, optionally watched over
  time), `send NAME ...` (connect then `duml_cli.py send`), `trace` (wraps `phone_usb_trace.py`).
- **`analyze_raw_capture.py`** — reconstructs the true accessory byte stream from the raw UDP
  capture log, segmented correctly by TCP connection (see the #64 writeup above for why that
  matters), and feeds it through the real `AoaMux` as one buffer to measure the discard rate
  with zero chunk-boundary ambiguity.
- **`analyze_bare_frames.py`** — deeper structural analysis of the #64 bug: per-read envelope/
  discard-run positions, whether discard runs span USB read-chunk boundaries, duplicate-frame
  detection, per-field "same as previous frame" rates for bare vs. enveloped frames, and a
  declared-length-vs-neighbouring-read-length lag search. Most of this came back negative
  (ruling things out) — see the #64 section above for what actually held up.
- **`phone_usb_trace.py`** — kernel ftrace wrapper for the phone's dwc3 USB gadget driver,
  intended to directly compare hardware-level TRB/giveback byte counts against the accessory
  read declared-length chain. **Unreliable on this phone's kernel build** — see the open-mystery
  section above before investing more time in it.

## Other fixes landed this session

- **Phone clock (#63):** the test phone's `persist.sys.timezone` was set to `GMT` instead of
  `Australia/Sydney`, explaining an observed `00:00` display during testing. Fixed live on
  device (`adb shell cmd alarm set-timezone Australia/Sydney`); not an app bug, no app code
  changed. Issue left open per the question-tracking convention (no code fix means no auto-close
  judgement call needed — see the issue itself for the full finding).
- **DUML schema migration continued:** three more commands (`GetVersion`/`CommonVersion`,
  `RcSignalQuality`, `GimbalPushParams`) migrated into the single canonical
  `docs/schema/duml/commands.yaml`, generator extended with new field kinds, Python call sites
  (`duml_telemetry.py`, `fw_version_check.py`) converted to use the generated decoders — landed
  in commit `eeeba1b`. Camera exposure/AE-lock `Set`/`Get` pairs were identified as the next good
  migration candidates but not done this session (schema currently only supports one `direction`
  per cmdset/cmdid, and several camera commands share an id between an empty-payload request and
  a payload-bearing reply).
- **UI cleanup:** `app/awto_dji_app/lib/ui/telemetry_screen.dart`'s Position and Attitude cards
  merged into one compact card with uniform small text; `app/awto_dji_app/lib/ui/
  about_screen.dart` now lists each active debug/data channel (accessory, TCP relay, raw UDP
  relay) with what's sent/received over each, instead of being silent about transport internals.
  Both verified visually via live device screenshots, not just `flutter analyze`.
