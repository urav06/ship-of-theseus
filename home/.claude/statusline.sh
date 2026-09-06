#!/usr/bin/env bash
# statusline.sh — Claude Code status line for Ghostty + FiraCode Nerd Font.
#
# Data flow: Claude Code pipes session JSON to stdin on every assistant
# message (debounced 300ms). This script reads it, extracts key fields
# with jq, and prints styled text to stdout for Ghostty to render.
#
# Requires: jq, FiraCode Nerd Font (or any Nerd Font).

set -euo pipefail

# ── Nerd Font glyphs ─────────────────────────────────────────────────────────
# Raw UTF-8 bytes — portable across bash 3.2+ (macOS ships 3.2).
ICON_CODE=$(printf '\xf3\xb1\x8c\xa3')   # U+F1323 nf-md-hammer_wrench
ICON_KNOW=$(printf '\xe2\x8c\xac')      # U+232C  benzene ring
ICON_FOLDER=$(printf '\xef\x81\xbb')    # U+F07B  nf-fa-folder
ICON_MODEL=$(printf '\xf3\xb1\x9c\x99') # U+F1719 nf-md-robot_happy
ICON_CLOCK=$(printf '\xef\x80\x97')     # U+F017  nf-fa-clock (5h window)
ICON_CALENDAR=$(printf '\xef\x81\xb3')  # U+F073  nf-fa-calendar (7d window)
ICON_BRANCH=$(printf '\xee\x9c\xa5')    # U+E725  nf-dev-git_branch

# ── ANSI escape helpers ──────────────────────────────────────────────────────
RST='\033[0m'
DIM='\033[38;5;245m'   # soft gray — visible but clearly secondary
BOLD='\033[1m'
CYAN='\033[38;5;87m'     # light cyan — project name + icon
STEEL='\033[38;5;67m'    # steel — robot, clock, calendar icons
GREEN='\033[38;5;42m'    # mint
YELLOW='\033[38;5;214m'  # amber
RED='\033[38;5;204m'     # coral

# Maps a 0–100 percentage to green/yellow/red.
threshold_color() {
  local pct=${1:-0}
  if   (( pct >= 90 )); then printf '%s' "$RED"
  elif (( pct >= 70 )); then printf '%s' "$YELLOW"
  else                        printf '%s' "$GREEN"
  fi
}

# ── Parse session JSON from stdin ────────────────────────────────────────────
input=$(cat)
field() { echo "$input" | jq -r "$1 // empty" 2>/dev/null; }

model=$(field '.model.display_name')
project_dir=$(field '.workspace.project_dir')
current_dir=$(field '.workspace.current_dir')

# Context: used_percentage is computed from input tokens (including cache).
# Truncate to integer — sub-percent precision is noise.
ctx_pct=$(field '.context_window.used_percentage')
ctx_pct=${ctx_pct%%.*}
ctx_pct=${ctx_pct:-0}

# Rate limits: absent before first API response — handled gracefully below.
rate_5h=$(field '.rate_limits.five_hour.used_percentage')
rate_7d=$(field '.rate_limits.seven_day.used_percentage')
reset_5h=$(field '.rate_limits.five_hour.resets_at')
reset_7d=$(field '.rate_limits.seven_day.resets_at')

# ── Project detection ────────────────────────────────────────────────────────
# ~/code/<name>/...     → code project   (icon: hammer-wrench)
# ~/Projects/<name>/... → knowledge work (icon: benzene ring)
# anything else         → standalone     (icon: folder, no project label)
#
# The project name is always the first path component after the root.
# Deeper nesting doesn't matter — ~/code/foo/bar/baz is still project "foo".
icon="$ICON_FOLDER"
project=""

case "$project_dir" in
  "$HOME"/code/*)
    icon="$ICON_CODE"
    project="${project_dir#"$HOME"/code/}"
    project="${project%%/*}"
    ;;
  "$HOME"/Projects/*)
    icon="$ICON_KNOW"
    project="${project_dir#"$HOME"/Projects/}"
    project="${project%%/*}"
    ;;
esac

# ── Context bar ──────────────────────────────────────────────────────────────
# 10-segment gauge: ▓ filled, ░ empty.
# Color shifts at 70% (yellow) and 90% (red).
ctx_color=$(threshold_color "$ctx_pct")
filled=$(( ctx_pct / 10 ))
bar=""
for (( i = 0; i < 10; i++ )); do
  if (( i < filled )); then bar+="▓"; else bar+="░"; fi
done

# ── Rate limits ──────────────────────────────────────────────────────────────
# Only rendered once available (null before first API response).
# Each shows usage % and a dimmed countdown to reset.

# Formats an epoch timestamp as a relative countdown: "2h14m", "3d5h", etc.
countdown() {
  local resets_at=$1 now diff hours mins days
  [[ -z "$resets_at" ]] && return
  now=$(date +%s)
  diff=$(( resets_at - now ))
  (( diff <= 0 )) && { printf 'now'; return; }
  days=$(( diff / 86400 ))
  hours=$(( (diff % 86400) / 3600 ))
  mins=$(( (diff % 3600) / 60 ))
  if (( days > 0 )); then printf '%dd%dh' "$days" "$hours"
  elif (( hours > 0 )); then printf '%dh%dm' "$hours" "$mins"
  else printf '%dm' "$mins"
  fi
}

rates=""
if [[ -n "$rate_5h" ]]; then
  r5=$(printf '%.0f' "$rate_5h")
  r5c=$(threshold_color "$r5")
  r5t=$(countdown "$reset_5h")
  rates="${STEEL}${ICON_CLOCK}${RST} ${r5c}${r5}%${RST}"
  [[ -n "$r5t" ]] && rates+=" ${DIM}${r5t}${RST}"
fi
if [[ -n "$rate_7d" ]]; then
  r7=$(printf '%.0f' "$rate_7d")
  r7c=$(threshold_color "$r7")
  r7t=$(countdown "$reset_7d")
  rates="${rates} ${DIM}·${RST} ${STEEL}${ICON_CALENDAR}${RST} ${r7c}${r7}%${RST}"
  [[ -n "$r7t" ]] && rates+=" ${DIM}${r7t}${RST}"
fi

# ── Separators ───────────────────────────────────────────────────────────────
SEP="${DIM}│${RST}"      # major sections (thin vertical)
DOT="${DIM}·${RST}"      # sub-items within a group
ARR="${DIM}›${RST}"      # line 2 separator

# ── Line 1: identity + health ────────────────────────────────────────────────
#   ［icon project］│ robot model │ ▓▓░░░░░░░░ 28% │ clock 15% 2h14m · cal 5% 3d0h
label="${project:-$(basename "$current_dir")}"
line1="${DIM}［${RST}${CYAN}${icon} ${BOLD}${CYAN}${label}${RST}${DIM}］${RST} ${SEP} ${STEEL}${ICON_MODEL}${RST} ${model} ${SEP} ${ctx_color}${bar}${RST} ${ctx_color}${ctx_pct}%${RST}"
if [[ -n "$rates" ]]; then
  line1+=" ${SEP} ${rates}"
fi

# ── Line 2: path + git branch (dimmed) ────────────────────────────────────────
display_path=$(echo "$current_dir" | sed "s|^$HOME|~|")
line2="${DIM}${display_path}${RST}"

PURPLE='\033[38;5;141m'
branch=$(git -C "$current_dir" branch --show-current 2>/dev/null || true)
if [[ -n "$branch" ]]; then
  line2+=" ${ARR} ${PURPLE}${ICON_BRANCH} ${branch}${RST}"
fi

# ── Render ────────────────────────────────────────────────────────────────────
printf '%b\n' "$line1"
printf '%b\n' "$line2"
