# .zprofile — login shell only. PATH and one-time session setup.

# ── Homebrew ──────────────────────────────────────────────────────────────────
# Sets HOMEBREW_PREFIX and adds brew binaries to PATH.
# Done here (not .zshrc) so HOMEBREW_PREFIX is available as a plain
# variable in every subsequent file — no $(brew --prefix) subshell needed.
eval "$(/opt/homebrew/bin/brew shellenv)"

# ── PATH ──────────────────────────────────────────────────────────────────────
# ~/.local/bin: uv, uvx, and any user-installed binaries.
export PATH="$HOME/.local/bin:$PATH"

# ── XDG runtime ──────────────────────────────────────────────────────────────
# macOS has no XDG_RUNTIME_DIR. $TMPDIR is per-user, per-session, and
# system-cleaned — the closest macOS equivalent. Lives in .zprofile because
# it depends on $TMPDIR (set by macOS before login shell) and the mkdir
# side-effect should only run once per session.
export XDG_RUNTIME_DIR="${TMPDIR}runtime-$(id -u)"
[ -d "$XDG_RUNTIME_DIR" ] || { mkdir -p "$XDG_RUNTIME_DIR" && chmod 0700 "$XDG_RUNTIME_DIR"; }

## The End ##