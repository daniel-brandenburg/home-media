FROM mcr.microsoft.com/dotnet/sdk:10.0 AS dev_container_auto_added_stage_label

ARG TZ=Etc/UTC
ENV TZ="$TZ"

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
        tmux \
        cron \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# GitHub CLI
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# No SSH keys in the container (gh authenticates over HTTPS); prefer HTTPS remotes.
RUN git config --global url."https://github.com/".insteadOf "git@github.com:" \
    && git config --global url."https://".insteadOf "git@"

# Cron jobs baked in as the ubuntu user
COPY cronscripts/ /home/ubuntu/cronscripts/
COPY cronjobs /home/ubuntu/cronjobs
RUN chmod +x /home/ubuntu/cronscripts/*.sh \
    && mkdir -p /home/ubuntu/cronlogs \
    && chown -R ubuntu:ubuntu /home/ubuntu/cronscripts /home/ubuntu/cronlogs /home/ubuntu/cronjobs \
    && crontab -u ubuntu /home/ubuntu/cronjobs \
    && echo "ubuntu ALL=(root) NOPASSWD: /usr/sbin/service cron start" > /etc/sudoers.d/ubuntu-cron \
    && chmod 0440 /etc/sudoers.d/ubuntu-cron

# Native installers as ubuntu user
USER ubuntu
ENV HOME=/home/ubuntu
ENV PATH="/home/ubuntu/.local/bin:${PATH}"

RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash

WORKDIR /workspaces
