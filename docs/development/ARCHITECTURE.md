# Architecture reference

## Staged Windows-native architecture

The Python process below remains the production implementation during migration. The parallel `native/` .NET 10 solution enforces these boundaries:

- `LongJumpReplay.Core`: UI-independent replay state and bounded frame retention.
- `LongJumpReplay.Video.Windows`: `IVideoSource`, synthetic validation source, and the isolated Media Foundation camera boundary.
- `LongJumpReplay.Infrastructure`: backward-compatible JSON loading and atomic persistence primitives.
- `LongJumpReplay.App`: WPF presentation and keyboard commands; no capture loop runs on the dispatcher thread.
- `LongJumpReplay.Tests`: dependency-free executable regression gate.

The native preview proves the synthetic Live/Freeze/Replay slice. `MediaFoundationCameraSource` also implements friendly-name enumeration, CPU BGRA delivery, monotonic timestamps, real-time latest-frame acquisition, bounded disposal, and operator selection with synthetic fallback, but it has not been exercised against physical hardware. The Python camera pipeline remains authoritative until native mode negotiation, buffering, encoding, reconnect, and hardware tests pass.

The authoritative product and engineering rules are in `PROJECT.KNOWLEDGE.md`. This document is a compact module and responsibility map.

## Process model

The app is one Python process with a Tkinter GUI thread and several bounded background workers.

```text
Tk main thread
├─ MainWindow and widgets
├─ playback state
├─ timeline/model updates
├─ queue polling
└─ shutdown coordination

Background workers
├─ capture
├─ JPEG encoding
├─ attempt collection/MP4 encoding
├─ export
├─ Take-off Assist
└─ Shuttle HID polling
```

## Ownership boundaries

- `CaptureEngine` owns camera/source lifecycle and frame ingestion.
- `TimeRingBuffer` owns rolling JPEG packets and memory/time eviction.
- `AttemptManager` owns preserved attempt media and cache lifecycle.
- `PlaybackController` owns Live/Replay navigation state.
- `CompetitionSession` owns athlete/round assignment and advancement.
- `MainWindow` orchestrates the above and should not become the owner of low-level encoding or capture logic.

## Main object creation

`app.py` loads `AppConfig`, creates the Tk root, and creates `MainWindow`. `MainWindow` creates the ring buffer, capture engine, attempt manager, playback controller, competition session, UI components, hotkey router, and optional Shuttle poller.

## Attempt lifecycle

```text
create_attempt
→ snapshot pre-roll
→ collect post-roll
→ encode temporary MP4
→ READY
→ optional decision/evidence/export
→ retention cleanup or manual deletion
```

`rotation_completed` and `counts_for_rotation` determine competition progress independently of media readiness and verdict.

## GUI update discipline

`MainWindow._tick()` is a presentation loop, not a capture loop. Keep it cheap. Status, attempts, timeline, and preview each have independent effective refresh limits. Hidden/minimized/menu/window-interaction states reduce work.

## Persistence

- Config: JSON, atomic replace.
- Attempt metadata: JSON sidecars in temporary cache.
- Attempt video: temporary MP4, with writer fallback where necessary.
- Evidence: raw and annotated PNG plus JSON.
- Event package: optional export bundle.

## Refactoring direction

`src/main_window.py` is the current integration hub and is large. Future refactors should extract controllers by domain while preserving tests:

- `CompetitionController`
- `AttemptReviewController`
- `CalibrationController`
- `ApplicationLifecycleController`
- `ExportRecoveryController`

Do not perform a wholesale rewrite. Extract one behavior with tests at a time.
