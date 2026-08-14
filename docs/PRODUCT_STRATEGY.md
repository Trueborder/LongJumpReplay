# LongJumpReplay product strategy

LongJumpReplay is a professional video-assistance system for the long-jump take-off-board judge. It complements AK2 and other competition systems; it does not replace them.

## Product boundary

```text
Camera
   -> LongJumpReplay
        -> replay and board-line inspection
        -> Valid / Foul / Review
        -> durable evidence and athlete/attempt context
        -> optional import/export adapter
             -> AK2 or another competition system
```

The camera never estimates jump distance. Distance is entered and exchanged as whole centimetres; wind remains in m/s. Both are optional values from an operator, import, or future documented device adapter.

## Priority classification

| Feature area | Classification | Delivery rule |
|---|---|---|
| Camera, bounded live buffer, Freeze/Live, frame stepping, shuttle/keyboard control, zoom/pan, board line | **CORE** | Optimize for instant, predictable judging and multi-hour stability. |
| Valid/Foul/Review/Not Decided, current athlete/attempt, history, evidence frame, crash-safe records | **CORE** | A verdict must be durable before the workflow advances; temporary-media expiry must not erase it. |
| Evidence package, clean/annotated separation, hashes, timestamps, camera and line metadata | **CORE** | Keep evidence reconstructable and export it only on operator request. |
| Bib, name, club, category, start order, attempt number, optional distance/wind | **USEFUL** | Keep lightweight, incomplete-data tolerant, and secondary to video. |
| CSV/XLSX/JSON roster import and generic CSV/JSON decision export | **USEFUL** | Use Parse -> Preview -> Validate -> Confirm -> Commit and stable adapter interfaces. |
| Basic local board/standings and manually selected finalists | **USEFUL** | Retain only where they improve operator awareness; keep modular. |
| Verified AK2 import/export and documented hardware adapters | **DEFER** | Implement only with official samples/protocols and interoperability tests. |
| PDF result sheets, XLSX result books, advanced rankings/ties, publishing, complex category administration | **DEFER** | Do not delay adjudication reliability or responsiveness. |
| Complete AK2 emulation, undocumented "AK2 compatible" output, mandatory internet/cloud/account | **REMOVE / AVOID** | Outside the product boundary. |

## Acceptance order

1. No attempt, verdict, or evidence-metadata loss.
2. Camera/buffer stability and bounded memory/disk behavior.
3. Correct athlete and attempt association.
4. Freeze/Live and frame-navigation accuracy under rapid input.
5. Evidence persistence and recovery after interruption.
6. Competition Board synchronization and safe roster import.
7. Optional distance/wind and generic interchange.
8. Verified external integrations.

Field-test reports stay local and should include attempts processed, verdict counts, corrections, decision latency, crashes/recovery warnings, dropped frames, missing evidence, and skipped distance entries. No personal telemetry is transmitted by default.
