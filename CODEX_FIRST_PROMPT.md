# First prompt to paste into Codex

```text
Read AGENTS.md and PROJECT.KNOWLEDGE.md completely, then inspect the repository without changing files. Run git status, summarize the architecture in your own words, identify the main runtime threads and data flow, list the non-negotiable workflow rules, and run the existing test suite. Do not implement anything yet. Report any mismatch between the documentation and the code, any tests that fail, and the three highest-risk areas for future changes.
```

After Codex completes that onboarding task, give it one focused change at a time. A good task prompt contains:

```text
Goal:
Current behavior:
Expected behavior:
Steps to reproduce:
Constraints that must remain true:
Tests to add or update:
```

Example:

```text
Goal: reduce CPU usage while the app is minimized.
Current behavior: capture continues correctly, but preview/timeline callbacks still consume noticeable CPU.
Expected behavior: recording and buffering continue at full configured quality, while all hidden/minimized presentation work drops to the Quiet-level refresh rate.
Constraints: do not reduce evidence quality, do not stop capture, and preserve clean shutdown.
Tests: add a test proving presentation callbacks are throttled while capture remains active.
```
