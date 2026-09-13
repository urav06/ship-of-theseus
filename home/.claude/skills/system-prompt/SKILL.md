---
name: system-prompt
description: Capture the exact system prompt and request Claude Code is currently sending, for reading, diffing, or reuse.
disable-model-invocation: true
---

Run the bundled script and report the three paths it prints:

```
python3 ~/.claude/skills/system-prompt/capture.py
```

It starts a local listener, launches a real interactive session against it, sends one message, and writes the captured request to `$XDG_STATE_HOME/claude-system-prompt/`: `request.json` (exact request), `system-prompt.md` (all system blocks, readable), and `main-block.txt` (the one block `--system-prompt` replaces). No headers are recorded.
