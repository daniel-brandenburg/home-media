"""
deploy.py — main pyinfra deploy entry point for home-media

Runs all tasks in order:
  1. system      — install required host packages, create directory structure
  2. config      — upload app config files (Caddyfile, dashy conf.yml, etc.)
  3. quadlets    — sync quadlet unit files to /etc/containers/systemd/
  4. systemd_    — sync home-media.target, daemon-reload, enable all services
  5. firewall    — open required ports in firewalld

Run with:
    pyinfra deploy/inventory.py deploy/deploy.py

To run a single task file independently (e.g. just push new config):
    pyinfra deploy/inventory.py deploy/tasks/config.py

For the one-time arr wiring (run after the stack is up):
    pyinfra deploy/inventory.py deploy/tasks/arr_setup.py
"""

from pyinfra import local

local.include("deploy/tasks/system.py")
local.include("deploy/tasks/config.py")
local.include("deploy/tasks/quadlets.py")
local.include("deploy/tasks/systemd.py")
local.include("deploy/tasks/firewall.py")
