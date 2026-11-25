#!/usr/bin/env bash
# Runs inside an agent devcontainer as postCreateCommand (as the "ubuntu" user).
# Shared by every template under devcontainers/.
#
# /opt/claude-config is a read-only bind mount of REMOTE_DIR/claude-config on the
# server (uploaded by deploy/tasks/devcontainers.py from this repo's claude-config/).
# It holds a snapshot of the operator's ~/.claude: CLAUDE.md, settings.json,
# statusline.sh, rules/, agents/, skills/.
set -euo pipefail

SRC=/opt/claude-config
CLAUDE="$HOME/.claude"   # a named volume (agent-claude-config), shared by all sandboxes

mkdir -p "$CLAUDE"

# ~/.claude.json is a file outside ~/.claude; keep it inside the volume so Claude
# Code's state persists across containers.
if [ -e "$HOME/.claude.json" ] && [ ! -L "$HOME/.claude.json" ]; then
    mv "$HOME/.claude.json" "$CLAUDE/.claude.json"
fi
ln -sf "$CLAUDE/.claude.json" "$HOME/.claude.json"

# No SSH keys in the sandbox: use HTTPS remotes, authenticated by gh.
git config --global url."https://github.com/".insteadOf "git@github.com:"
git config --global url."https://".insteadOf "git@"
git config --global credential.https://github.com.helper '!gh auth git-credential'

if [ ! -d "$SRC" ]; then
    echo "setup: $SRC is not mounted; skipping Claude config." >&2
    exit 0
fi

# Live links: deploying new skills/agents/rules shows up without recreating the container.
link() {
    [ -e "$SRC/$1" ] || return 0
    if [ -e "$CLAUDE/$1" ] && [ ! -L "$CLAUDE/$1" ]; then
        echo "setup: $CLAUDE/$1 exists and is not a symlink; leaving it alone." >&2
    else
        ln -sfn "$SRC/$1" "$CLAUDE/$1"
    fi
}
for item in skills agents rules CLAUDE.md; do
    link "$item"
done

# Copies (not links): Claude Code rewrites settings.json, and the status line must be
# executable. The one host-specific path in settings.json is the statusLine command.
# Re-run this script to pick up a newly deployed settings.json without recreating.
if [ -f "$SRC/settings.json" ]; then
    sed "s#/home/[^/\"]*/\\.claude/#$HOME/.claude/#g" "$SRC/settings.json" > "$CLAUDE/settings.json"
fi
if [ -f "$SRC/statusline.sh" ]; then
    install -m 755 "$SRC/statusline.sh" "$CLAUDE/statusline.sh"
fi
