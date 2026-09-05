# .zshrc — interactive shell only.

# -- Completion ----------------------------------------------------------------
# fpath must be extended before compinit runs.
# mkdir guard must run before compinit tries to write the dump file.
# 24h check avoids a full rebuild on every shell open.
setopt EXTENDED_GLOB
fpath=("$HOMEBREW_PREFIX/share/zsh-completions" $fpath)
[[ -d "$XDG_CACHE_HOME/zsh" ]] || mkdir -p "$XDG_CACHE_HOME/zsh"
autoload -Uz compinit
if [[ -n "$XDG_CACHE_HOME/zsh/zcompdump"(#qN.mh+24) ]]; then
  compinit -d "$XDG_CACHE_HOME/zsh/zcompdump"
else
  compinit -C -d "$XDG_CACHE_HOME/zsh/zcompdump"
fi

# -- History -------------------------------------------------------------------
# HISTFILE set here (not .zshenv) because /etc/zshrc runs between them
# and would overwrite it. Setting it here wins.
[[ -d "$XDG_STATE_HOME/zsh" ]] || mkdir -p "$XDG_STATE_HOME/zsh"
export HISTFILE="$XDG_STATE_HOME/zsh/history"
HISTSIZE=10000
SAVEHIST=10000
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_FIND_NO_DUPS
setopt SHARE_HISTORY
setopt EXTENDED_HISTORY

# -- Plugins -------------------------------------------------------------------
# Order matters: fzf-tab → autosuggestions → syntax-highlighting.
# fzf-tab is a git clone of Aloxaf/fzf-tab (no brew formula exists; needs fzf).
source "$XDG_DATA_HOME/zsh/plugins/fzf-tab/fzf-tab.plugin.zsh"
source "$HOMEBREW_PREFIX/share/zsh-autosuggestions/zsh-autosuggestions.zsh"
source "$HOMEBREW_PREFIX/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"

# -- FZF -----------------------------------------------------------------------
# Ctrl+R: history  Ctrl+T: file picker  Alt+C: cd picker
source <(fzf --zsh)
export FZF_DEFAULT_COMMAND="fd --type f --hidden --follow --exclude .git"
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_ALT_C_COMMAND="fd --type d --hidden --follow --exclude .git"

# fzf-tab: directory preview when completing cd
zstyle ':fzf-tab:complete:cd:*' fzf-preview 'eza -1 --color=always $realpath'
zstyle ':completion:*:descriptions' format '[%d]'
zstyle ':completion:*' list-colors ${(s.:.)LS_COLORS}
zstyle ':completion:*' menu no

# -- Zoxide --------------------------------------------------------------------
# Smarter cd. `z foo` jumps to your most frecent match for "foo".
eval "$(zoxide init zsh)"

# -- Aliases -------------------------------------------------------------------
alias ls="eza --icons=auto"
alias l="eza -lah --icons=auto --git"
alias la="eza -lah --icons=auto --git"
alias ll="eza -lh --icons=auto --git"
alias tree="eza --tree --icons=auto"
alias cat="bat"
export MANPAGER="sh -c 'col -bx | bat -l man -p'"

# -- Venv auto-activate --------------------------------------------------------
# Activates .venv on cd, deactivates on leave. Works with zoxide.
_auto_venv() {
  if [[ -f .venv/bin/activate ]]; then
    [[ "$VIRTUAL_ENV" != "$PWD/.venv" ]] && source .venv/bin/activate
  elif [[ -n "$VIRTUAL_ENV" ]]; then
    deactivate
  fi
}

# -- Directory tinting ---------------------------------------------------------
# Subtly shifts Ghostty's background via OSC 11 based on project root.
# Gives each workspace a distinct feel so tabs are visually distinguishable,
# even while a full-screen TUI (Claude Code, etc.) is running.
_auto_tint() {
  case "$PWD" in
    $HOME/code|$HOME/code/*)         printf '\e]11;#20252f\e\\' ;;  # deep steel — code
    $HOME/Projects|$HOME/Projects/*) printf '\e]11;#292733\e\\' ;;  # muted violet — projects
    *)                               printf '\e]11;#282c34\e\\' ;;  # default
  esac
}

# -- chpwd hooks ---------------------------------------------------------------
autoload -Uz add-zsh-hook
add-zsh-hook chpwd _auto_venv
add-zsh-hook chpwd _auto_tint
_auto_venv  # run once for the starting directory
_auto_tint

# -- Starship ------------------------------------------------------------------
eval "$(starship init zsh)"


## The End ##
