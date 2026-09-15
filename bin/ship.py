#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""ship: a drift check for the copy lane, and a capture of Claude Code's system prompt.

`home/` mirrors `~`. `system/` mirrors `/`. The machine reads `~/.config` through a
symlink, so the files under it are live and need no copy. Every other tracked file
under a mirror is a copy. The repo holds one version and the machine holds another.
Any difference between the two is drift.

    ship.py check [PATH ...]   Compare the index copy of each copy-lane file with the
                               live file. Print the `cp` that ends each difference.
    ship.py capture            Record the request that Claude Code sends. Write the
                               main system block to .claude/agents/default.local.md.

A PATH is a repo path. A directory selects every tracked file below it. The list of
copy-lane files is git's index, read with `git ls-files`. Nothing here copies a file.
You run the `cp` yourself. lefthook runs `check` on staged files, so a commit cannot
record a copy that the machine does not run.

uv reads the inline metadata above and picks the interpreter. If no installed Python
satisfies it, `uv run` downloads one over the network.
"""

from __future__ import annotations

import argparse
import difflib
import http.server
import json
import os
import pty
import select
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]
MIRRORS = {"home": Path.home(), "system": Path("/")}


def git(*args: str) -> bytes:
    """Run git at the repo root and return its stdout. Git prints its own errors to the terminal."""
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, stdout=subprocess.PIPE
    ).stdout


# --- copy lane ----------------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    """One tracked file under a mirror, with the index mode and its live path."""

    rel: str
    mode: str
    live: Path

    @property
    def repo(self) -> Path:
        return ROOT / self.rel

    @property
    def executable(self) -> bool:
        return self.mode == "100755"


def manifest() -> list[Entry]:
    """Every tracked file under a mirror that is not already live."""
    entries: list[Entry] = []
    for record in git("ls-files", "-z", "-s", "--full-name", "--", *MIRRORS).split(
        b"\0"
    ):
        if not record:
            continue
        meta, rel = record.decode().split("\t", 1)
        mode = meta.split()[0]
        top, _, rest = rel.partition("/")
        live = MIRRORS[top] / rest
        entry = Entry(rel, mode, live)
        if live.exists() and live.resolve() == entry.repo.resolve():
            continue  # the machine reads this file through a symlink, so it is live
        entries.append(entry)
    return entries


def select_entries(paths: list[str]) -> list[Entry]:
    """Keep the entries under the given repo paths. With no paths, keep every entry."""
    entries = manifest()
    if not paths:
        return entries
    wanted: set[str] = set()
    for p in paths:
        resolved = Path(p).resolve()
        if resolved.is_relative_to(ROOT):
            wanted.add(str(resolved.relative_to(ROOT)))
        else:
            print(f"ignored  {p}: outside the repo")
    selected = [
        e
        for e in entries
        if any(e.rel == w or e.rel.startswith(w + "/") for w in wanted)
    ]
    if not selected:
        print("nothing to check: no copy-lane file among the given paths")
    return selected


def index_bytes(entry: Entry) -> bytes:
    return git("show", f":{entry.rel}")


def is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)


def show_diff(label_a: str, a: bytes, label_b: str, b: bytes) -> None:
    try:
        lines = difflib.unified_diff(
            a.decode().splitlines(keepends=True),
            b.decode().splitlines(keepends=True),
            fromfile=label_a,
            tofile=label_b,
        )
    except UnicodeDecodeError:
        print(f"  binary files differ: {label_a} {label_b}")
        return
    for line in lines:
        sys.stdout.write(
            line if line.endswith("\n") else f"{line}\n\\ No newline at end of file\n"
        )


def resolutions(entry: Entry) -> str:
    """The two plain commands that end the drift. One makes the repo win, one the machine."""
    repo, live = shlex.quote(str(entry.repo)), shlex.quote(str(entry.live))
    sudo = "sudo " if entry.rel.startswith("system/") else ""
    return f"  repo wins:    {sudo}cp {repo} {live}\n  machine wins: cp {live} {repo}"


def check(paths: list[str]) -> int:
    """Return 1 when any selected copy-lane file differs from its live file."""
    drift = 0
    for entry in select_entries(paths):
        if not entry.live.exists():
            print(f"missing  {entry.live}\n{resolutions(entry)}")
            drift += 1
            continue
        try:
            live = entry.live.read_bytes()
        except OSError as err:
            print(f"unreadable  {entry.live}: {err.strerror}")
            drift += 1
            continue
        staged = index_bytes(entry)
        if staged != live:
            print(f"drift    {entry.rel}  !=  {entry.live}")
            show_diff(f"index:{entry.rel}", staged, str(entry.live), live)
            print(resolutions(entry))
            drift += 1
        elif entry.executable != is_executable(entry.live):
            live_mode = "executable" if is_executable(entry.live) else "not executable"
            print(f"mode     {entry.rel}: index {entry.mode}, live {live_mode}")
            print(resolutions(entry))
            drift += 1
        else:
            print(f"ok       {entry.rel}")
    if drift:
        print(f"\n{drift} file(s) drift. Run the cp you mean, then stage again.")
        return 1
    return 0


# --- system prompt capture ----------------------------------------------------
#
# Claude Code sends its system prompt as a list of text blocks. The facts about
# this machine (working directory, git status, date) arrive in a separate system
# turn, so the blocks are the same for every session of one version on a machine
# with the same integrations. The longest block is the main prompt. `--agent` and
# `--system-prompt` replace that block and no other. The capture keeps it verbatim,
# including the sections that exist only because of what this machine has enabled.

STATE_DIR = (
    Path(os.environ.get("XDG_STATE_HOME", "~/.local/state")).expanduser()
    / "claude-system-prompt"
)
AGENT_PATH = ROOT / ".claude" / "agents" / "default.local.md"


class Capture(http.server.BaseHTTPRequestHandler):
    """Record every request body. Answer with an API error, so the session stops there."""

    bodies: ClassVar[list[bytes]] = []  # capture() clears this before each run

    def do_POST(self) -> None:
        self.bodies.append(self.rfile.read(int(self.headers.get("content-length", 0))))
        self.send_response(500)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(
            b'{"type":"error","error":{"type":"api_error","message":"captured by ship.py"}}'
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def chat_request(bodies: list[bytes]) -> dict[str, object] | None:
    """The first request that carries a system prompt and tools. Earlier requests are probes."""
    for body in bodies:
        if b'"system"' in body and b'"tools"' in body:
            return json.loads(body)
    return None


def run_session(base_url: str) -> None:
    """Drive one interactive claude session through a pty until the listener holds a chat request."""
    env = dict(
        os.environ,
        ANTHROPIC_BASE_URL=base_url,
        ENABLE_TOOL_SEARCH="true",  # a custom base URL turns tool search off otherwise
        TERM="xterm-256color",
        COLUMNS="120",
        LINES="40",
    )
    os.chdir(ROOT)
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe("claude", ["claude"], env)
    start = time.monotonic()
    sent = False
    while time.monotonic() - start < 60 and chat_request(Capture.bodies) is None:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if ready:
            try:
                os.read(fd, 65536)
            except OSError:
                break
        if not sent and time.monotonic() - start > 6:
            os.write(fd, b"hi\r")
            sent = True
    os.kill(pid, signal.SIGKILL)


def capture() -> int:
    Capture.bodies.clear()
    server = http.server.HTTPServer(("127.0.0.1", 0), Capture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    run_session(f"http://127.0.0.1:{server.server_address[1]}")
    server.shutdown()

    req = chat_request(Capture.bodies)
    if req is None:
        print("no chat request captured", file=sys.stderr)
        return 1
    system = req["system"]
    tools = req.get("tools")
    if not isinstance(system, list):
        print("unexpected request shape: system is not a list", file=sys.stderr)
        return 1
    n_tools = len(tools) if isinstance(tools, list) else 0
    main = max(system, key=lambda block: len(block.get("text", "")))["text"].strip("\n")
    if any(str(Path.home()) in block.get("text", "") for block in system):
        print(
            "a system block names this machine's home; refusing to write it",
            file=sys.stderr,
        )
        return 1
    version = subprocess.run(
        ["claude", "--version"], check=True, capture_output=True, text=True
    ).stdout.split()[0]
    today = datetime.now(UTC).date()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "request.json").write_text(json.dumps(req, indent=2))
    with (STATE_DIR / "system-prompt.md").open("w") as f:
        f.write(
            f"# Claude Code system prompt capture\n\nmodel: {req.get('model')}\nclaude: {version}\n"
        )
        f.write(f"captured: {today}\nsystem blocks: {len(system)}\ntools: {n_tools}\n")
        for i, block in enumerate(system):
            text = block.get("text", "")
            f.write(
                f"\n\n---\n\n## Block {i} ({len(text)} chars, cache_control={block.get('cache_control')})\n\n{text}"
            )

    AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENT_PATH.write_text(
        "---\n"
        "name: default\n"
        f"description: Claude Code's main system block as this machine rendered it on {today} "
        f"(claude {version}, interactive session), for reading, diffing, and deriving agents.\n"
        "---\n"
        f"{main}\n"
    )
    print(f"captured claude {version}: {len(system)} system blocks, {n_tools} tools")
    print(f"request:  {STATE_DIR / 'request.json'}")
    print(f"readable: {STATE_DIR / 'system-prompt.md'}")
    print(f"agent:    {AGENT_PATH}")
    return 0


# --- entry point ---------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ship.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check").add_argument(
        "paths",
        nargs="*",
        help="repo paths to limit to (default: every copy-lane file)",
    )
    sub.add_parser("capture")
    args = parser.parse_args(argv)
    try:
        return capture() if args.command == "capture" else check(args.paths)
    except subprocess.CalledProcessError as err:
        print(
            f"{' '.join(map(str, err.cmd[:2]))} failed with exit status {err.returncode}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
