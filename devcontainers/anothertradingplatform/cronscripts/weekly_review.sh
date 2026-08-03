#!/bin/bash
set -euo pipefail
# cron runs with a minimal PATH — kimi's installer puts the binary in
# ~/.kimi-code/bin, claude in ~/.local/bin.
export PATH="$HOME/.kimi-code/bin:$HOME/.local/bin:$PATH"
# Run inside the mounted workspace (/workspaces/<repo>) so the audit targets
# the repo, not $HOME.
cd /workspaces/*/
kimi --model "kimi-k2.7-code" -p "You are to complete /codebase-audit"
