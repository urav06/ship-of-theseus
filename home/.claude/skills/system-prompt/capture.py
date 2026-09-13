#!/usr/bin/env python3
"""Capture the exact request Claude Code sends, including the system prompt.

Starts a local HTTP listener, launches an interactive `claude` session against it
through a pseudo-terminal, sends one message, and records the first request body.
Headers (and therefore the OAuth token) are never written.
"""
import http.server, json, os, pty, select, sys, threading, time, signal

OUT_DIR = os.path.expanduser(os.environ.get("XDG_STATE_HOME", "~/.local/state")) + "/claude-system-prompt"
PORT = 8765
raw_path = os.path.join(OUT_DIR, "request.json")
md_path = os.path.join(OUT_DIR, "system-prompt.md")
main_path = os.path.join(OUT_DIR, "main-block.txt")   # the one block --system-prompt replaces
captured = []   # list of (path, body)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        captured.append((self.path, body))
        self.send_response(500)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"type":"error","error":{"type":"api_error","message":"captured by capture.py"}}')
    def log_message(self, *a): pass

server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

env = dict(os.environ, ANTHROPIC_BASE_URL=f"http://127.0.0.1:{PORT}", TERM="xterm-256color", COLUMNS="120", LINES="40")
pid, fd = pty.fork()
if pid == 0:
    os.execvpe("claude", ["claude"], env)

deadline = time.time() + 60
sent = False
start = time.time()
def have_prompt():
    return any(b'"system"' in body and b'"tools"' in body for _, body in captured)
while time.time() < deadline and not have_prompt():
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try: os.read(fd, 65536)
        except OSError: break
    if not sent and time.time() - start > 6:
        os.write(fd, b"hi\r"); sent = True
os.kill(pid, signal.SIGKILL)
server.shutdown()

print("requests seen:", [(path, sorted(json.loads(body).keys())[:6]) for path, body in captured])
main = [body for _, body in captured if b'"system"' in body and b'"tools"' in body]
if not main:
    sys.exit("no chat request with a system prompt captured")
req = json.loads(main[0])
os.makedirs(OUT_DIR, exist_ok=True)
with open(raw_path, "w") as f: json.dump(req, f, indent=2)
with open(md_path, "w") as f:
    f.write(f"# Claude Code system prompt capture\n\nmodel: {req.get('model')}\n")
    f.write(f"system blocks: {len(req['system'])}\ntools: {len(req.get('tools', []))}\n\n")
    for i, b in enumerate(req["system"]):
        f.write(f"\n\n---\n\n## Block {i} ({len(b.get('text',''))} chars, cache_control={b.get('cache_control')})\n\n")
        f.write(b.get("text", ""))
with open(main_path, "w") as f:
    f.write(req["system"][-1].get("text", ""))
print(f"captured: model={req.get('model')} system_blocks={len(req['system'])} tools={len(req.get('tools', []))}")
print(f"raw: {raw_path}\nreadable: {md_path}\nmain block only: {main_path}")
