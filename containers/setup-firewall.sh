#!/usr/bin/env bash
set -euo pipefail

# Opens all host ports required by the home-media stack in firewalld.
# Run this once on the MicroOS server after first deployment.
# Safe to re-run — firewalld ignores ports that are already open.
#
# Usage (on the remote server):
#   sudo bash /srv/containers/setup-firewall.sh
#
# Or remotely from the developer machine:
#   ssh db@mediaserver 'sudo bash /srv/containers/setup-firewall.sh'

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[34m%s\033[0m\n' "$*"; }
step()  { echo; blue "==> $*"; }

require() {
  command -v "$1" &>/dev/null || { red "Missing required tool: $1"; exit 1; }
}
require firewall-cmd

# ---------------------------------------------------------------------------
# Port definitions
# Format: "PORT/PROTOCOL  SERVICE  DESCRIPTION"
# ---------------------------------------------------------------------------

# TCP-only ports
declare -a TCP_PORTS=(
  "80     caddy          HTTP reverse proxy"
  "443    caddy          HTTPS reverse proxy"
  "3333   bitmagnet      HTTP UI and API"
  "3334   bitmagnet      DHT crawler (TCP)"
  "4545   listenarr      Audiobook automation"
  "6881   qbittorrent    BitTorrent peer traffic (TCP)"
  "7878   radarr         Movie automation"
  "8080   qbittorrent    WebUI"
  "8083   calibre-web    Ebook library"
  "8084   shelfmark      Ebook downloader"
  "8081   dashy          Dashboard"
  "8096   jellyfin       Media streaming"
  "8989   sonarr         TV automation"
  "9696   prowlarr       Indexer management"
  "13378  audiobookshelf Audiobook server"
)

# UDP-only ports
declare -a UDP_PORTS=(
  "3334   bitmagnet      DHT crawler (UDP)"
  "6881   qbittorrent    BitTorrent peer traffic (UDP)"
)

# ---------------------------------------------------------------------------
# Open ports
# ---------------------------------------------------------------------------

open_port() {
  local port="$1"
  local proto="$2"
  local service="$3"
  local desc="$4"

  if firewall-cmd --query-port="${port}/${proto}" --permanent &>/dev/null; then
    green "  [${proto}] ${port} already open (${service}: ${desc})"
  else
    firewall-cmd --permanent --add-port="${port}/${proto}"
    green "  [${proto}] ${port} opened (${service}: ${desc})"
  fi
}

step "Opening TCP ports"
for entry in "${TCP_PORTS[@]}"; do
  read -r port service desc <<< "$entry"
  open_port "$port" tcp "$service" "$desc"
done

step "Opening UDP ports"
for entry in "${UDP_PORTS[@]}"; do
  read -r port service desc <<< "$entry"
  open_port "$port" udp "$service" "$desc"
done

# ---------------------------------------------------------------------------
# Reload firewalld to apply permanent rules
# ---------------------------------------------------------------------------

step "Reloading firewalld"
firewall-cmd --reload
green "  firewalld reloaded"

echo
blue "==> All ports are open. Current active rules:"
firewall-cmd --list-ports
