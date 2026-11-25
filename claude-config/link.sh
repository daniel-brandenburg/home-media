#!/usr/bin/env bash
# Create the (git-ignored) symlinks in this directory that point at your local
# ~/.claude. The deploy (deploy/tasks/devcontainers.py) follows them and uploads
# the real files to REMOTE_DIR/claude-config on the server, where every agent
# devcontainer mounts them read-only at /opt/claude-config (see setup.sh).
#
# Usage: claude-config/link.sh            # source: ~/.claude
#        CLAUDE_SRC=/other/dir claude-config/link.sh
set -euo pipefail

src="${CLAUDE_SRC:-$HOME/.claude}"
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for item in CLAUDE.md settings.json statusline.sh rules agents skills; do
    if [ -e "$src/$item" ]; then
        ln -sfn "$src/$item" "$dir/$item"
        echo "linked  $item -> $src/$item"
    else
        echo "skipped $item (not found in $src)" >&2
    fi
done
