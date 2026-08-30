# .zshenv — loaded for every shell, always. Keep lean: env vars only.

# ── XDG ──────────────────────────────────────────────────────────────────────
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"
export XDG_CACHE_HOME="$HOME/.cache"

# ── Zsh ───────────────────────────────────────────────────────────────────────
# Bootstrap: tells zsh where to find all other dotfiles (~/.config/zsh/).
# Must live here — it's the only file zsh reads before knowing ZDOTDIR.
export ZDOTDIR="$XDG_CONFIG_HOME/zsh"

# ── macOS ─────────────────────────────────────────────────────────────────────
# Prevents .zsh_sessions/ from being written to ~.
export SHELL_SESSIONS_DISABLE=1

# ── Default tools ─────────────────────────────────────────────────────────────
# EDITOR must be in .zshenv so non-interactive processes (git, cron) see it.
# --wait makes Zed block until the file is closed, required for git commit etc.
export EDITOR="zed --wait"

# ── Tool config paths ─────────────────────────────────────────────────────────
export RIPGREP_CONFIG_PATH="$XDG_CONFIG_HOME/ripgrep/config"
export IPYTHONDIR="$XDG_CONFIG_HOME/ipython"
export JUPYTER_CONFIG_DIR="$XDG_CONFIG_HOME/jupyter"
export JUPYTER_DATA_DIR="$XDG_DATA_HOME/jupyter"
# STATE not RUNTIME: Jupyter's "runtime" includes cookie secrets that benefit
# from persisting across reboots. XDG_RUNTIME_DIR is tmpdir-backed on macOS.
export JUPYTER_RUNTIME_DIR="$XDG_STATE_HOME/jupyter"
# Cache only — matplotlib bundles config+cache into one dir. Only a font cache
# lives here; per-project style via plt.rcParams is more reproducible.
export MPLCONFIGDIR="$XDG_CACHE_HOME/matplotlib"
export GNUPGHOME="$XDG_DATA_HOME/gnupg"

# ── Python ───────────────────────────────────────────────────────────────────
# Stops venv's activate script from mutating PS1. Starship already detects
# $VIRTUAL_ENV and renders the venv name itself — letting both manage the
# prompt fights over who owns _OLD_VIRTUAL_PS1 and breaks starship in tabs
# spawned inside a venv directory.
export VIRTUAL_ENV_DISABLE_PROMPT=1

## The End ##
