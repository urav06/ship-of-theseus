#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""ship: a drift check for the copy lane, and a capture of Claude Code's system prompt.

`home/` mirrors `~`. `system/` mirrors `/`. The machine reads `~/.config` through a
symlink, so the files under it are live and need no copy. Every other tracked file
under a mirror is a copy. The repo holds a copy and the machine holds its own file.
Any difference between the two is drift.

    ship.py check [PATH ...]   Compare each copy, as git's index holds it, with the
                               machine's file. Print the `cp` that ends each difference.
    ship.py capture            Record the request that Claude Code sends. Write the
                               main system block to .claude/agents/default.local.md.

A PATH is a file or directory inside the repo, relative to where you run the command.
A directory selects every copy below it, so `check .` covers wherever you stand. The
list of copy-lane files is git's index, read with `git ls-files`. Nothing here copies
a file. You run the `cp` yourself. lefthook runs `check` on staged files, so a commit
cannot record a copy that the machine does not run.

uv reads this script's inline metadata and picks a Python 3.14 interpreter,
downloading one if none is installed.
"""

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
from typing import ClassVar, Self, override

ROOT = Path(__file__).resolve().parents[1]
MIRRORS = {"home": Path.home(), "system": Path("/")}


def git(*args: str) -> bytes:
    """Run git at the repo root and return its stdout. Git prints its own errors to the terminal."""
    return subprocess.run(["git", *args], cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout


# --- copy lane ----------------------------------------------------------------


@dataclass(frozen=True)
class Copy:
    """One tracked file under a mirror: its path in the repo, its index mode, and the machine's file."""

    path: Path
    mode: str
    machine: Path

    @classmethod
    def from_record(cls, record: bytes) -> Self:
        """Parse one `git ls-files -s` record: `<mode> <object> <stage>\\t<path>`."""
        meta, path = record.decode().split("\t", 1)
        top, _, rest = path.partition("/")
        return cls(Path(path), meta.split()[0], MIRRORS[top] / rest)

    @property
    def repo(self) -> Path:
        return ROOT / self.path

    @property
    def executable(self) -> bool:
        return self.mode == "100755"

    @property
    def is_live(self) -> bool:
        """The machine reads this file through a symlink into the repo, so there is nothing to copy."""
        return self.machine.resolve() == self.repo.resolve()


def copies() -> list[Copy]:
    """Every tracked file under a mirror that is not already live."""
    records = git("ls-files", "-z", "-s", "--", *MIRRORS).split(b"\0")[:-1]
    return [copy for copy in map(Copy.from_record, records) if not copy.is_live]


def select_copies(paths: list[str]) -> list[Copy]:
    """Keep the copies at or below the given paths. No paths means the whole repo."""
    wanted: set[Path] = set()
    for path in paths or [str(ROOT)]:
        resolved = Path(path).resolve()
        if resolved.is_relative_to(ROOT):
            wanted.add(resolved.relative_to(ROOT))
        else:
            print(f"ignored  {path}: outside the repo")

    selected = [c for c in copies() if any(c.path.is_relative_to(w) for w in wanted)]
    if not selected:
        print("nothing to check: no copy-lane file among the given paths")
    return selected


def show_diff(copy: Copy, in_index: bytes, on_machine: bytes) -> None:
    index_label, machine_label = f"index:{copy.path}", str(copy.machine)
    try:
        old, new = in_index.decode(), on_machine.decode()
    except UnicodeDecodeError:
        print(f"  binary files differ: {index_label} {machine_label}")
        return

    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=index_label,
        tofile=machine_label,
    )
    sys.stdout.writelines(
        line if line.endswith("\n") else f"{line}\n\\ No newline at end of file\n" for line in lines
    )


def resolutions(copy: Copy) -> str:
    """The two plain commands that end the drift. One makes the repo win, one the machine."""
    repo, machine = shlex.quote(str(copy.repo)), shlex.quote(str(copy.machine))
    sudo = "sudo " if copy.path.is_relative_to("system") else ""
    return f"  repo wins:    {sudo}cp {repo} {machine}\n  machine wins: cp {machine} {repo}"


def report(copy: Copy) -> bool:
    """Print how this copy compares with the machine's file. True when the two differ."""
    try:
        on_machine = copy.machine.read_bytes()
    except FileNotFoundError:
        print(f"missing  {copy.machine}\n{resolutions(copy)}")
        return True
    except OSError as err:
        print(f"unreadable  {copy.machine}: {err.strerror}")
        return True

    in_index = git("show", f":{copy.path}")
    machine_executable = bool(copy.machine.stat().st_mode & 0o111)

    if in_index != on_machine:
        print(f"drift    {copy.path}  !=  {copy.machine}")
        show_diff(copy, in_index, on_machine)
    elif copy.executable != machine_executable:
        state = "executable" if machine_executable else "not executable"
        print(f"mode     {copy.path}: index {copy.mode}, machine {state}")
    else:
        print(f"ok       {copy.path}")
        return False
    print(resolutions(copy))
    return True


def check(paths: list[str]) -> int:
    """Return 1 when any selected copy differs from the machine's file."""
    drift = sum(map(report, select_copies(paths)))
    if drift:
        print(f"\n{drift} file(s) drift. Run the cp you mean, then stage again.")
    return 1 if drift else 0


# --- system prompt capture ----------------------------------------------------
#
# Claude Code sends its system prompt as a list of text blocks. The facts about
# this machine (working directory, git status, date) arrive in a separate system
# turn, so the blocks are the same for every session of one version on a machine
# with the same integrations. The longest block is the main prompt. `--agent` and
# `--system-prompt` replace that block and no other. The capture keeps it verbatim,
# including the sections that exist only because of what this machine has enabled.

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", "~/.local/state")).expanduser() / "claude-system-prompt"
REQUEST_PATH = STATE_DIR / "request.json"
READABLE_PATH = STATE_DIR / "system-prompt.md"
AGENT_PATH = ROOT / ".claude" / "agents" / "default.local.md"


class Listener(http.server.BaseHTTPRequestHandler):
    """Record every request body. Answer with an API error, so the session stops there."""

    requests: ClassVar[list[bytes]] = []

    def do_POST(self) -> None:
        self.requests.append(self.rfile.read(int(self.headers.get("content-length", 0))))
        self.send_response(500)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"type":"error","error":{"type":"api_error","message":"captured by ship.py"}}')

    @override
    def log_message(self, format: str, *args: object) -> None:
        return


def chat_request(requests: list[bytes]) -> dict[str, object] | None:
    """The first request that carries a system prompt and tools. Earlier requests are probes."""
    return next((json.loads(body) for body in requests if b'"system"' in body and b'"tools"' in body), None)


def drain(fd: int, until: float) -> bool:
    """Read and discard claude's terminal output until `until`, so claude never blocks on a full pty.

    True when time ran out with the session still waiting. False once a chat request has arrived
    or the terminal has closed."""
    while time.monotonic() < until:
        if chat_request(Listener.requests) is not None:
            return False
        if select.select([fd], [], [], 0.2)[0]:
            try:
                os.read(fd, 65536)
            except OSError:
                return False
    return True


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
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(ROOT)
        os.execvpe("claude", ["claude"], env)

    start = time.monotonic()
    if drain(fd, until=start + 6):
        os.write(fd, b"hi\r")  # type a first message once the TUI has had time to start
        drain(fd, until=start + 60)
    os.kill(pid, signal.SIGKILL)


def capture() -> int:
    server = http.server.HTTPServer(("127.0.0.1", 0), Listener)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    run_session(f"http://127.0.0.1:{server.server_address[1]}")
    server.shutdown()

    # refuse before writing anything
    request = chat_request(Listener.requests)
    if request is None:
        print("no chat request captured", file=sys.stderr)
        return 1
    system = request["system"]
    if not isinstance(system, list):
        print("unexpected request shape: system is not a list", file=sys.stderr)
        return 1
    texts = [block.get("text", "") for block in system]
    if any(str(Path.home()) in text for text in texts):
        print("a system block names this machine's home; refusing to write it", file=sys.stderr)
        return 1

    # what the files record
    tools = request.get("tools")
    tool_count = len(tools) if isinstance(tools, list) else 0
    main_block = max(texts, key=len).strip("\n")
    version = subprocess.run(
        ["claude", "--version"], check=True, capture_output=True, text=True
    ).stdout.split()[0]
    today = datetime.now(UTC).date()
    readable = (
        "# Claude Code system prompt capture\n\n"
        f"model: {request.get('model')}\n"
        f"claude: {version}\n"
        f"captured: {today}\n"
        f"system blocks: {len(system)}\n"
        f"tools: {tool_count}\n"
    ) + "".join(
        f"\n\n---\n\n## Block {i} ({len(text)} chars, cache_control={block.get('cache_control')})\n\n{text}"
        for i, (block, text) in enumerate(zip(system, texts))
    )
    agent = (
        "---\n"
        "name: default\n"
        f"description: Claude Code's main system block as this machine rendered it on {today} "
        f"(claude {version}, interactive session), for reading, diffing, and deriving agents.\n"
        "---\n"
        f"{main_block}\n"
    )

    # write
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REQUEST_PATH.write_text(json.dumps(request, indent=2))
    READABLE_PATH.write_text(readable)
    AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENT_PATH.write_text(agent)

    print(f"captured claude {version}: {len(system)} system blocks, {tool_count} tools")
    print(f"request:  {REQUEST_PATH}")
    print(f"readable: {READABLE_PATH}")
    print(f"agent:    {AGENT_PATH}")
    return 0


# --- entry point --------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ship.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check").add_argument(
        "paths", nargs="*", help="files or directories to check (default: the whole repo)"
    )
    commands.add_parser("capture")
    args = parser.parse_args(argv)

    try:
        return capture() if args.command == "capture" else check(args.paths)
    except subprocess.CalledProcessError as err:
        print(f"{' '.join(map(str, err.cmd[:2]))} failed with exit status {err.returncode}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
