#!/usr/bin/env python3
"""Capture the exact request Claude Code sends and refresh the local `default` agent.

Starts a local HTTP listener, launches an interactive `claude` session against it
through a pseudo-terminal, sends one message, and records the request bodies.
Headers (and therefore the OAuth token) are never written.

Outputs:
  $XDG_STATE_HOME/claude-system-prompt/request.json      the exact chat request
  $XDG_STATE_HOME/claude-system-prompt/system-prompt.md  all system blocks, readable
  ~/.claude/agents/default.local.md                       agent whose body is Anthropic's
                                                          main system block (untracked)

The session runs with --exclude-dynamic-system-prompt-sections so the captured
main block carries no per-machine sections (cwd, env, git status) and is stable
across machines for a given Claude Code version.
"""

import http.server
import json
import os
import pty
import select
import signal
import subprocess
import sys
import threading
import time
from datetime import date

STATE_DIR = os.path.join(
    os.path.expanduser(os.environ.get("XDG_STATE_HOME", "~/.local/state")),
    "claude-system-prompt",
)
AGENT_PATH = os.path.expanduser("~/.claude/agents/default.local.md")
PORT = 8765
captured = []  # (path, body)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        captured.append((self.path, body))
        self.send_response(500)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(
            b'{"type":"error","error":{"type":"api_error","message":"captured by capture.py"}}'
        )

    def log_message(self, *a):
        pass


def have_prompt():
    return any(b'"system"' in body and b'"tools"' in body for _, body in captured)


server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

env = dict(
    os.environ,
    ANTHROPIC_BASE_URL=f"http://127.0.0.1:{PORT}",
    TERM="xterm-256color",
    COLUMNS="120",
    LINES="40",
)
pid, fd = pty.fork()
if pid == 0:
    os.execvpe("claude", ["claude", "--exclude-dynamic-system-prompt-sections"], env)

start = time.time()
sent = False
while time.time() - start < 60 and not have_prompt():
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try:
            os.read(fd, 65536)
        except OSError:
            break
    if not sent and time.time() - start > 6:
        os.write(fd, b"hi\r")
        sent = True
os.kill(pid, signal.SIGKILL)
server.shutdown()

main = [body for _, body in captured if b'"system"' in body and b'"tools"' in body]
if not main:
    sys.exit("no chat request with a system prompt captured")
req = json.loads(main[0])
version = (
    subprocess.run(["claude", "--version"], capture_output=True, text=True)
    .stdout.strip()
    .split()[0]
)

os.makedirs(STATE_DIR, exist_ok=True)
with open(os.path.join(STATE_DIR, "request.json"), "w") as f:
    json.dump(req, f, indent=2)
with open(os.path.join(STATE_DIR, "system-prompt.md"), "w") as f:
    f.write(
        f"# Claude Code system prompt capture\n\nmodel: {req.get('model')}\nclaude: {version}\ncaptured: {date.today()}\n"
    )
    f.write(
        f"system blocks: {len(req['system'])}\ntools: {len(req.get('tools', []))}\n"
    )
    for i, b in enumerate(req["system"]):
        f.write(
            f"\n\n---\n\n## Block {i} ({len(b.get('text', ''))} chars, cache_control={b.get('cache_control')})\n\n"
        )
        f.write(b.get("text", ""))

os.makedirs(os.path.dirname(AGENT_PATH), exist_ok=True)
with open(AGENT_PATH, "w") as f:
    f.write("---\n")
    f.write("name: default\n")
    f.write(
        f"description: Anthropic's default Claude Code system prompt, captured from {version} on {date.today()}. Same as a plain session.\n"
    )
    f.write("---\n")
    f.write(req["system"][-1].get("text", ""))

print(
    f"captured: model={req.get('model')} claude={version} system_blocks={len(req['system'])} tools={len(req.get('tools', []))}"
)
print(f"request:  {os.path.join(STATE_DIR, 'request.json')}")
print(f"readable: {os.path.join(STATE_DIR, 'system-prompt.md')}")
print(f"agent:    {AGENT_PATH}")
