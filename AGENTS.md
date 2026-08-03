# Codex instructions for Long Jump Replay

Read `PROJECT.KNOWLEDGE.md` before making any nontrivial change. It is the source of truth for architecture, workflow, invariants, testing, known limitations, and release practices.

## Required behavior

- Preserve optional judging: `Not decided` must not block the next athlete by default.
- Keep live capture running while replay is frozen.
- Keep frozen/selected attempts independent from rolling-buffer expiry.
- Keep the timeline playhead fixed and reuse canvas items.
- Never update Tkinter widgets from worker threads.
- New settings with performance impact need a description and a Low/Medium/High/Very high badge.
- New user-facing text must be translated in English and Czech.
- Do not silently reduce evidence quality through a performance preset.
- Shutdown must remain bounded and clean.
- Every project change must include a relevant update to `PROJECT.KNOWLEDGE.md` in the same change, even when the implementation change is small.

## Before editing

1. Run `git status`.
2. Read the relevant implementation and tests.
3. Reproduce the issue with the smallest test or synthetic source.

## After editing

```powershell
python -m pytest
python app.py --self-test
```

For GUI changes, also run:

```powershell
python app.py --synthetic --windowed
```

Do not claim physical camera, ShuttleXpress, or frozen Windows EXE validation unless you actually performed it.
