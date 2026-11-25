# Devcontainer for the alarmclock project (Claude Code / Kimi Code).
#
# Toolchain: Flutter SDK + C toolchain (gcc via build-essential, gdb,
# valgrind) for app/, PlatformIO for the ESP32 firmware/, and uv with its
# own Python 3.13 for scripts/ (ubuntu:24.04 ships 3.12, scripts/ needs
# >=3.13).
#
# Dart/Flutter SDK only — no Android SDK/Gradle/emulator (a large download
# that this template doesn't need). This template covers
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
        gdb \
        valgrind \
        python3 \
        python3-venv \
        pipx \
        jq \
        tmux \
        cron \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# GitHub CLI — not in Debian's default repos, installed from GitHub's own apt
# repo per https://github.com/cli/cli/blob/trunk/docs/install_linux.md
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# The ubuntu user (UID/GID 1000) already exists in the ubuntu:24.04 base image
# and matches the server's default host user.
# No SSH keys in the container (gh authenticates over HTTPS); prefer HTTPS remotes.
RUN git config --global url."https://github.com/".insteadOf "git@github.com:" \
    && git config --global url."https://".insteadOf "git@"

# Scheduled agent prompts: scripts + crontab are baked into the image and
# installed as the ubuntu user's crontab. The cron daemon itself is started by
# devcontainer.json's postStartCommand (no systemd in the container).
COPY cronscripts/ /home/ubuntu/cronscripts/
COPY cronjobs /home/ubuntu/cronjobs
RUN chmod +x /home/ubuntu/cronscripts/*.sh \
    && mkdir -p /home/ubuntu/cronlogs \
    && chown -R ubuntu:ubuntu /home/ubuntu/cronscripts /home/ubuntu/cronlogs /home/ubuntu/cronjobs \
    && crontab -u ubuntu /home/ubuntu/cronjobs \
    && echo "ubuntu ALL=(root) NOPASSWD: /usr/sbin/service cron start" > /etc/sudoers.d/ubuntu-cron \
    && chmod 0440 /etc/sudoers.d/ubuntu-cron

# Flutter SDK (stable channel, shallow clone) + native installers, all as the
# ubuntu user into ~/flutter and ~/.local/bin.
USER ubuntu
ENV HOME=/home/ubuntu
RUN git clone --depth 1 -b stable https://github.com/flutter/flutter.git /home/ubuntu/flutter
ENV PATH="/home/ubuntu/flutter/bin:/home/ubuntu/.local/bin:${PATH}"
# Pre-fetch Dart/Flutter tool artifacts at build time so the first `flutter`
# invocation inside the container doesn't have to download them.
RUN flutter precache --linux --no-android --no-ios && flutter doctor
# PlatformIO for firmware/ (ESP32). Pre-fetch the espressif32 platform,
# xtensa toolchain, and Arduino framework at build time by compiling a
# throwaway project, so they are cached in the image rather than downloaded on
# first use. Project lib_deps are still resolved at runtime.
RUN pipx install platformio \
    && mkdir -p /tmp/pio-warm/src \
    && printf '[env:esp32dev]\nplatform = espressif32\nboard = esp32dev\nframework = arduino\nboard_build.filesystem = littlefs\n' > /tmp/pio-warm/platformio.ini \
    && printf 'void setup() {}\nvoid loop() {}\n' > /tmp/pio-warm/src/main.cpp \
    && pio run -d /tmp/pio-warm \
    && rm -rf /tmp/pio-warm
# uv for scripts/ (requires Python >= 3.13; uv installs its own). Python 3.13
# is pre-fetched at build time for the same reason as above.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv python install 3.13
RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash

# CodeGraph CLI: the global settings.json runs `codegraph prompt-hook` on every prompt.
# Pinned to the operator's version; bump deliberately.
ARG CODEGRAPH_VERSION=v1.6.0
RUN curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | CODEGRAPH_VERSION="$CODEGRAPH_VERSION" sh

WORKDIR /workspaces
