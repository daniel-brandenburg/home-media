"""
deploy.py — main pyinfra deploy entry point for home-media

Runs all tasks in order:
  1. system      — install required host packages, create directory structure
  2. tailscale   — install tailscaled, enable service, optionally authenticate
  3. config      — upload app config files (dashy conf.yml, qbit conf with hashed credentials, etc.)
  4. quadlets    — sync quadlet unit files to /etc/containers/systemd/
  5. systemd_    — sync home-media.target, daemon-reload, enable all services
  6. firewall    — open required ports in firewalld (assigns tailscale0 zone)
  7. arr_setup   — wait for all services to be ready, then wire up *arr + qBittorrent

Run with:
    pyinfra deploy/inventory.py deploy/deploy.py

To run a single task file independently (e.g. just push new config):
    pyinfra deploy/inventory.py deploy/tasks/config.py

To install/update Tailscale only:
    pyinfra deploy/inventory.py deploy/tasks/tailscale.py
"""

from pyinfra import local

local.include("deploy/tasks/system.py")
local.include("deploy/tasks/config.py")
local.include("deploy/tasks/quadlets.py")
local.include("deploy/tasks/systemd.py")
local.include("deploy/tasks/firewall.py")
local.include("deploy/tasks/arr_setup.py")
