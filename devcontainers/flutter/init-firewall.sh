#!/bin/bash
# Default-deny egress firewall for the Flutter devcontainer.
#
# Adapted from Anthropic's reference implementation
# (https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh),
# with two changes:
#   1. DNS is restricted to the container's actual configured resolver(s),
#      not any destination on port 53 — the upstream script allows DNS to
#      anywhere, which is a known data-exfiltration vector via DNS tunneling
#      (see https://github.com/anthropics/claude-code/issues/36907).
#   2. The blanket "allow outbound SSH to anywhere" rule is dropped. GitHub's
#      SSH IP ranges are already covered by the "git" key in GitHub's /meta
#      API response, added to the allowed-domains ipset below, so git-over-ssh
#      to GitHub still works without opening port 22 to arbitrary hosts.
#
# No Android SDK/Gradle is installed in this template (see Dockerfile), so
# Google Maven / Gradle plugin portal / dl.google.com are deliberately NOT
# allowlisted below — only pub.dev (package resolution) and
# storage.googleapis.com (Flutter/Dart SDK artifacts) are added on top of
# the base Claude/Kimi/GitHub set.
set -euo pipefail
IFS=$'\n\t'

# 1. Extract Docker/Podman's internal DNS rules BEFORE any flushing
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

if [ -n "$DOCKER_DNS_RULES" ]; then
    echo "Restoring container-engine DNS rules..."
    iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
    iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
    echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
fi

# Only allow DNS to the resolver(s) actually configured for this container
# (not to arbitrary destinations on port 53). IPv6 resolvers are skipped here
# since this script is IPv4-only — IPv6 is blocked wholesale below instead.
mapfile -t RESOLVERS < <(awk '/^nameserver/ {print $2}' /etc/resolv.conf)
if [ "${#RESOLVERS[@]}" -eq 0 ]; then
    echo "ERROR: no nameserver found in /etc/resolv.conf"
    exit 1
fi
ipv4_resolver_found=0
for resolver in "${RESOLVERS[@]}"; do
    if [[ ! "$resolver" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        echo "Skipping non-IPv4 resolver: $resolver"
        continue
    fi
    echo "Allowing DNS to resolver: $resolver"
    iptables -A OUTPUT -p udp -d "$resolver" --dport 53 -j ACCEPT
    iptables -A INPUT -p udp -s "$resolver" --sport 53 -j ACCEPT
    ipv4_resolver_found=1
done
if [ "$ipv4_resolver_found" -eq 0 ]; then
    echo "ERROR: no IPv4 nameserver found in /etc/resolv.conf"
    exit 1
fi

iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

ipset create allowed-domains hash:net

echo "Fetching GitHub IP ranges..."
gh_ranges=$(curl -s https://api.github.com/meta)
if [ -z "$gh_ranges" ]; then
    echo "ERROR: Failed to fetch GitHub IP ranges"
    exit 1
fi
if ! echo "$gh_ranges" | jq -e '.web and .api and .git' >/dev/null; then
    echo "ERROR: GitHub API response missing required fields"
    exit 1
fi

echo "Processing GitHub IPs..."
while read -r cidr; do
    if [[ ! "$cidr" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[0-9]{1,2}$ ]]; then
        echo "ERROR: Invalid CIDR range from GitHub meta: $cidr"
        exit 1
    fi
    echo "Adding GitHub range $cidr"
    ipset add allowed-domains "$cidr"
done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git)[]' | aggregate -q)

# Domains needed by: Claude Code, Kimi Code, and Dart/Flutter (pub.dev
# packages + Flutter/Dart SDK artifact storage).
# VERIFY: Kimi Code's runtime API domain(s) are not confirmed — only its
# installer host (code.kimi.com). Watch for connection failures after first
# login and add whatever domain the CLI actually talks to.
for domain in \
    "api.anthropic.com" \
    "claude.ai" \
    "statsig.anthropic.com" \
    "code.kimi.com" \
    "api.moonshot.ai" \
    "api.moonshot.cn" \
    "registry.npmjs.org" \
    "pub.dev" \
    "storage.googleapis.com"; do
    echo "Resolving $domain..."
    ips=$(dig +noall +answer A "$domain" | awk '$4 == "A" {print $5}')
    if [ -z "$ips" ]; then
        echo "WARNING: Failed to resolve $domain — skipping"
        continue
    fi
    while read -r ip; do
        if [[ ! "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            echo "ERROR: Invalid IP from DNS for $domain: $ip"
            exit 1
        fi
        echo "Adding $ip for $domain"
        ipset add allowed-domains "$ip"
    done < <(echo "$ips")
done

# Allow the container's own virtual subnet (the podman bridge gateway, e.g.
# 10.88.x.x — NOT the physical LAN; a container's default route never points
# at the host's real network unless run with --network=host).
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -z "$HOST_IP" ]; then
    echo "ERROR: Failed to detect host IP"
    exit 1
fi
HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
echo "Container bridge network detected as: $HOST_NETWORK"
iptables -A INPUT -s "$HOST_NETWORK" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT

iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

# This script only builds an IPv4 allowlist. Block IPv6 outright (loopback
# excepted) so it can't be used to bypass the allowlist above entirely.
if command -v ip6tables >/dev/null 2>&1; then
    ip6tables -F
    ip6tables -X
    ip6tables -A INPUT -i lo -j ACCEPT
    ip6tables -A OUTPUT -o lo -j ACCEPT
    ip6tables -P INPUT DROP
    ip6tables -P FORWARD DROP
    ip6tables -P OUTPUT DROP
fi

echo "Firewall configuration complete"
echo "Verifying firewall rules..."
if curl --connect-timeout 5 https://example.com >/dev/null 2>&1; then
    echo "ERROR: Firewall verification failed - was able to reach https://example.com"
    exit 1
else
    echo "Firewall verification passed - unable to reach https://example.com as expected"
fi

if ! curl --connect-timeout 5 https://api.github.com/zen >/dev/null 2>&1; then
    echo "ERROR: Firewall verification failed - unable to reach https://api.github.com"
    exit 1
else
    echo "Firewall verification passed - able to reach https://api.github.com as expected"
fi
