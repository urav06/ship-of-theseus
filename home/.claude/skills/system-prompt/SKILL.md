---
name: system-prompt
description: Refresh the local `default` agent with Anthropic's current Claude Code system prompt, and save the exact captured request for reading or diffing.
disable-model-invocation: true
---

Run the bundled script and report the paths it prints:

```
python3 ~/.claude/skills/system-prompt/capture.py
```

It starts a local listener, launches a real interactive session against it with per-machine sections excluded, sends one message, and writes: `~/.claude/agents/default.local.md` (untracked agent whose body is the current main system block, so `claude --agent default` equals a plain session) and, under `$XDG_STATE_HOME/claude-system-prompt/`, `request.json` (exact request) and `system-prompt.md` (all system blocks, readable). No headers are recorded.
