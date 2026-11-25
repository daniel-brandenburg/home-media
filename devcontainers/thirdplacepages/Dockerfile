# Devcontainer for the ThirdPlacePages project (Claude Code / Kimi Code).
#
# Toolchain: .NET 10 SDK (src/Server/global.json pins 10.0.100 with
# rollForward latestFeature) plus dotnet-ef, which docs/development.md expects
# as a global tool.
#
# No container engine inside: the backend tests that use Testcontainers
# (Postgres, RabbitMQ, MinIO, Mailpit, Keycloak), run.sh (Aspire) and
# scripts/test-all.sh will not work here. See README.md in this directory.
#
# Flutter is intentionally absent (being replaced by KMP). Add a JDK/Android
# SDK layer when src/Native exists.
FROM mcr.microsoft.com/dotnet/sdk:11.0

ARG TZ=Etc/UTC
ENV TZ="$TZ"

# sqlite3 is used by scripts/new-worktree.sh to snapshot the codegraph index.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        gnupg \
        sudo \
        unzip \
        build-essential \
        python3 \
        jq \
        sqlite3 \
        tmux \
        vim \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# GitHub CLI — not in Debian's default repos, installed from GitHub's own apt
# repo per https://github.com/cli/cli/blob/trunk/docs/install_linux.md
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# The ubuntu user (UID/GID 1000) already exists in the dotnet SDK (Ubuntu)
# base image and matches the server's default host user.

# scripts/new-worktree.sh creates worktrees in <repo>/../ThirdPlacePages_worktrees,
# i.e. /workspaces/ThirdPlacePages_worktrees. devcontainer.json mounts a named
# volume there; creating it here (owned by ubuntu) makes a fresh volume writable.
RUN mkdir -p /workspaces/ThirdPlacePages_worktrees \
    && chown ubuntu:ubuntu /workspaces/ThirdPlacePages_worktrees

# Native installers and dotnet global tools as the ubuntu user.
USER ubuntu
ENV HOME=/home/ubuntu
ENV PATH="/home/ubuntu/.local/bin:/home/ubuntu/.kimi-code/bin:/home/ubuntu/.dotnet/tools:${PATH}"

# No SSH keys live in the container; gh authenticates over HTTPS, so rewrite
# SSH-style GitHub remotes to HTTPS (for the ubuntu user's ~/.gitconfig).
RUN git config --global url."https://github.com/".insteadOf "git@github.com:" \
    && git config --global url."https://".insteadOf "git@"

# Version matches EF Core in src/Server/Directory.Packages.props.
RUN dotnet tool install --global dotnet-ef --version 10.0.11

RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash

# CodeGraph CLI: the global settings.json runs `codegraph prompt-hook` on every prompt.
# Pinned to the operator's version; bump deliberately.
ARG CODEGRAPH_VERSION=v1.6.0
RUN curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | CODEGRAPH_VERSION="$CODEGRAPH_VERSION" sh

WORKDIR /workspaces
