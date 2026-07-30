# Flutter devcontainer for the coding agent (Claude Code / Kimi Code).
#
# Dart/Flutter SDK only — no Android SDK/Gradle/emulator. That toolchain
# pulls from Google Maven, the Gradle plugin portal, and dl.google.com,
# which is a much wider (and harder to keep tight) runtime firewall
# allowlist than this default-deny setup aims for. This template covers
# `flutter analyze` / `flutter test` / `flutter build web` / `flutter build
# linux` — not `flutter build apk`/`appbundle`. Add Android SDK support as
# its own variant if mobile builds are needed.
FROM ubuntu:24.04

ARG TZ=Etc/UTC
ENV TZ="$TZ"

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        gnupg \
        sudo \
        unzip \
        xz-utils \
        zip \
        libglu1-mesa \
        clang \
        cmake \
        ninja-build \
        pkg-config \
        build-essential \
        tmux \
        iptables \
        ipset \
        iproute2 \
        dnsutils \
        aggregate \
        jq \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# GitHub CLI — not in Debian's default repos, installed from GitHub's own apt
# repo per https://github.com/cli/cli/blob/trunk/docs/install_linux.md
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Matches PUID=1000/PGID=1000 (this server's default host user). If your
# host user has a different UID/GID, update these two lines and rebuild.
RUN groupadd -g 1000 agent && useradd -m -u 1000 -g 1000 -s /bin/bash agent

COPY init-firewall.sh /usr/local/bin/init-firewall.sh
RUN chmod +x /usr/local/bin/init-firewall.sh \
    && echo "agent ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/agent-firewall \
    && chmod 0440 /etc/sudoers.d/agent-firewall

# Flutter SDK (stable channel, shallow clone) + native installers, all as the
# "agent" user into ~/flutter and ~/.local/bin.
USER agent
ENV HOME=/home/agent
RUN git clone --depth 1 -b stable https://github.com/flutter/flutter.git /home/agent/flutter
ENV PATH="/home/agent/flutter/bin:/home/agent/.local/bin:${PATH}"
# Pre-fetch Dart/Flutter tool artifacts at build time (network is open here,
# unlike at container runtime once init-firewall.sh has run) so the first
# `flutter` invocation inside the container doesn't need storage.googleapis.com.
RUN flutter precache --linux --no-android --no-ios && flutter doctor
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash

WORKDIR /workspaces
