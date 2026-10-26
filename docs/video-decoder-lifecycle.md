# Video decoder lifecycle recovery (#67)

Issue: <https://github.com/awto-au/awto-dji/issues/67>

## Evidence and scope

The live 26 October 2026 stack trace shows an uncaught `IllegalStateException`
from `MediaCodec.getInputBuffer()` on `video-decode`. That exception escaped the
thread and killed the app process, including its unrelated DUML session.

The original pending-queue monitor did serialize the input check with application
release. It did not turn an Android codec-state check into a guarantee that a
subsequent MediaCodec operation would succeed. `onError` only logged, output
release could also throw, and partial startup/cleanup failures had no recovery.
Posted drains read the shim's mutable current codec rather than identifying the
session that posted them. Configuration/start and teardown also ran outside the
callback worker.

None of this identifies what originally put this device's decoder in Released
state. Android codec reclamation, a vendor decoder failure, and application
lifecycle timing remain hypotheses. This patch handles exceptions and removes
cross-session work; it does not claim to reproduce that underlying device event.

## Ownership and transitions

`VideoShim` owns the Flutter texture and Surface on a per-texture session. One
`video-decode` HandlerThread is retained until engine cleanup. Each session's
`DecoderSession` owns its codec generation, input indices, queues and retry
budget. Creation, configure/start, buffer calls, stop and release run on that
worker, including across reconnects.

| Trigger | Result |
| --- | --- |
| `createTexture` | Retire old session, enqueue its teardown before replacement startup. Reply on main thread after codec startup. |
| Factory/configure/start failure | Release partial codec, return `video_init`, dispose Surface/texture. Existing Dart `VideoDecoder.start()` catches this and returns false; AOA connection continues. |
| Input/output exception or `onError` | Invalidate codec identity/generation, discard old indices and queued pictures, independently attempt stop and release, schedule replacement. |
| Recovery | At most three attempts per texture lifetime, with 250/500/1000 ms backoff. Reuse the Surface/texture. Cache SPS/PPS and wait for a subsequent IDR before resuming. |
| Retry budget exhausted | State `failed`; ignore video feeds. DUML transport remains owned by AoaTransport/AoaShim. New `createTexture` resets the budget. |
| `release` | Cancel synchronously, then release codec before Surface and texture. Queued callbacks/drains and delayed recovery cannot revive the session. |
| Engine cleanup | Unregister video channel; queue final teardown and quit worker safely. |

A fresh codec is used even for transient/recoverable errors: no assumptions are
made about the old asynchronous input-index ownership. Both Android
[`MediaCodec` error handling](https://developer.android.com/reference/android/media/MediaCodec#error-handling)
and [`CodecException`](https://developer.android.com/reference/android/media/MediaCodec.CodecException)
allow replacement after terminal errors. Diagnostic info and Android's
recoverable/transient flags are retained in the error log and `lastError` stats.

Recovery does not send DUML commands or force a reconnect. It waits for the
camera's next SPS/PPS/IDR as needed; there is no guaranteed time to first recovered
frame. The existing optional decoder bootstrap lookup is preserved.

The queue is bounded to 300 items and 8 MiB; feed wakeups are coalesced. Stats
retain fed/dropped/submitted/rendered/pending/available and add state, errors,
recoveries, lastError and awaitingIdr. A scheduled attempt counts in recoveries.
After explicit release, closed stats contain zero counters.

## Software verification

Run the 17 deterministic JUnit lifecycle tests without an Android/Flutter SDK:

```sh
python3 scripts/test_video_decoder.py
```

Requires Python 3 and Java 17+. The runner downloads SHA-256-pinned Kotlin 2.1.0
compiler/runtime and JUnit jars from Maven Central to ignored `tmp/` on first use.
The same tests are wired into Android's `testDebugUnitTest` task using the
project's configured Kotlin toolchain. A pull-request workflow runs the standalone
suite for Android and test-runner changes.

Coverage: release with queued input and callbacks; an independently invalidated
input buffer; queue/null-input/output failures; decoder errors; stale callbacks;
partial startup; cancellation before startup and during recovery; cleanup errors;
bounded retries even after successful restarts; repeated initialization and 20
reconnect cycles; bootstrap/SPS/PPS/IDR restoration; oversized inputs and bounded
queues; repeated close.

Verified in the fix workspace:

- All 17 lifecycle JUnit tests passed. Fake codecs assert every codec operation is
  on the worker. A subsequent unrelated task runs after the injected Released
  exception. This is not an on-device DUML continuity test.
- Both production Kotlin files compile against Android 14 APIs (Robolectric's
  unmodified android-all jar) and the official Flutter 3.35.7 embedding jar, using
  Kotlin 2.1.0 / JVM target 17. This checks real adapter signatures, not a full APK
  build or the project's newer Gradle/Kotlin/Flutter toolchain.
- 21 existing AOA/relay/dev-contract Python tests and 11 protocol checks passed.
- Python runner compilation and `git diff --check` passed.

The optional adapter check is reproducible with real API jars:

```sh
python3 scripts/test_video_decoder.py \
  --android-api-jar /path/to/android.jar \
  --flutter-embedding-jar /path/to/flutter_embedding_debug.jar
```

A full Flutter analysis/test run, Gradle Android test run and APK build were not
performed: this workspace lacks the project's Flutter/Dart 3.13.5 and Android SDK
installation. The lightweight runner intentionally does not claim those checks.

## Live validation still required

Use the project's normal Android/Flutter build environment, then bench-test with
the phone, RC and Phantom 3 video source:

1. Build the debug APK and run the full Flutter and Android unit-test suites.
2. Run continuous H.264 decoding beyond the original failure interval. Record
   logcat, app PID, video stats and the DUML receive/transmit session together.
3. Unplug/reconnect USB and repeat initialization while video is queued. Confirm
   old textures disappear, frames resume and decoder threads/resources do not
   accumulate. Only one worker should exist per attached Flutter engine.
4. Exercise a decoder error/reclamation where available. Check errors/recoveries,
   unchanged texture ID, return of rendered frames after a fresh IDR, and command
   traffic through the same still-running app process throughout recovery.
5. If recovery is exhausted, verify video becomes failed while DUML continues,
   and an explicit new texture/session can start video again.

Device codec behavior, actual recovery latency and continuous DUML survival have
not yet been verified. The precise original state-transition cause remains open.
