"""
deploy.py — main pyinfra deploy entry point for home-media

Runs all tasks in order:
  1. system      — install required host packages, create directory structure
  2. tailscale   — install tailscaled, enable service, optionally authenticate
  3. config      — upload app config files (dashy conf.yml, qbit init, etc.)
  4. quadlets    — sync quadlet unit files to /etc/containers/systemd/
  5. systemd_    — sync home-media.target, daemon-reload, enable all services
  6. firewall    — open required ports in firewalld (assigns tailscale0 zone)

Run with:
    pyinfra deploy/inventory.py deploy/deploy.py

To run a single task file independently (e.g. just push new config):
    pyinfra deploy/inventory.py deploy/tasks/config.py

To install/update Tailscale only:
    pyinfra deploy/inventory.py deploy/tasks/tailscale.py

For the one-time arr wiring (run after the stack is up):
    pyinfra deploy/inventory.py deploy/tasks/arr_setup.py
"""

from pyinfra import local

local.include("deploy/tasks/system.py")
local.include("deploy/tasks/tailscale.py")
local.include("deploy/tasks/config.py")
local.include("deploy/tasks/quadlets.py")
local.include("deploy/tasks/systemd.py")
local.include("deploy/tasks/firewall.py")
