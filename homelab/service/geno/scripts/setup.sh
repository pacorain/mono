#!/bin/sh
set -e

echo "=== Geno Provisioning Server Setup ==="

# Update package repository
apk update

# Install required packages
apk add --no-cache \
    dnsmasq \
    nginx \
    python3 \
    py3-pip \
    py3-flask \
    wget \
    syslinux

# Create directories
mkdir -p /var/lib/tftpboot
mkdir -p /srv/http/iso
mkdir -p /srv/http/answers
mkdir -p /srv/geno/state
mkdir -p /etc/geno

# Download Proxmox VE ISO
PROXMOX_ISO_URL="https://enterprise.proxmox.com/iso/proxmox-ve_9.1-1.iso"
wget -q -O /srv/http/iso/proxmox-ve.iso "$PROXMOX_ISO_URL"

# Create PXE configuration directory
mkdir -p /var/lib/tftpboot/pxelinux.cfg
cat > /var/lib/tftpboot/pxelinux.cfg/default <<'EOFPXE'
DEFAULT proxmox
LABEL proxmox
    KERNEL memdisk
    INITRD http://10.11.0.65/iso/proxmox-ve.iso
    APPEND iso raw
EOFPXE

# Copy PXE boot files
cp /usr/share/syslinux/pxelinux.0 /var/lib/tftpboot/
cp /usr/share/syslinux/*.c32 /var/lib/tftpboot/
cp /usr/share/syslinux/memdisk /var/lib/tftpboot/

# Configure dnsmasq for DHCP + TFTP
cat > /etc/dnsmasq.conf <<'EOF'
# Interface binding
interface=eth0
bind-interfaces

# DHCP configuration
# Start with no static reservations - these will be added dynamically
dhcp-range=10.11.0.2,10.11.0.6,255.255.252.0,12h

# Gateway
dhcp-option=3,10.11.0.1

# DNS servers
dhcp-option=6,8.8.8.8,1.1.1.1

# Proxmox answer file URL (option 250)
dhcp-option=250,http://10.11.0.65/answer

# PXE boot configuration
dhcp-boot=pxelinux.0

# Enable TFTP server
enable-tftp
tftp-root=/var/lib/tftpboot

# Additional DHCP configuration file for dynamic updates
dhcp-hostsfile=/etc/dnsmasq.hosts

# Logging
log-dhcp
log-queries
log-facility=/var/log/dnsmasq.log
EOF

# Create empty hosts file for dynamic updates
touch /etc/dnsmasq.hosts

# Configure nginx
cat > /etc/nginx/http.d/geno.conf <<'EOF'
server {
    listen 80;
    server_name _;

    root /srv/http;

    # Serve static files (ISO, installer)
    location /iso/ {
        autoindex on;
    }

    # Proxy to Python app for dynamic content
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

# Copy answer file template to geno directory
cat > /etc/geno/answer.toml.tpl <<'EOFTEMPLATE'
[global]
keyboard = en-us
country = US
fqdn = {{ hostname }}.rwhq.net
timezone = America/New_York
mailto = austin@rainwater.family
root-password-hashed = {{ root_password_hashed }}
root-ssh-keys = {{ ssh_public_key }}
reboot-on-error = false

[network]
source = from-answer
cidr = {{ ip }}/22
dns = 8.8.8.8
gateway = 10.11.0.1/22

[disk-setup]
filesystem = ext4
disk_list = ["nvme0n1"]

[post-installation-webhook]
url = http://10.11.0.65/post-proxmox-install
EOFTEMPLATE

# Copy node names queue
cat > /etc/geno/names <<'EOFNAMES'
peach-beach
moo-moo-meadows
toads-turnpike
sherbert-land
EOFNAMES

# Create Python provisioning app
cat > /srv/geno/app.py <<'EOFPYTHON'
#!/usr/bin/env python3
"""Geno provisioning server - progressive node configuration."""

import json
import os
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

STATE_FILE = Path("/srv/geno/state/state.json")
NAMES_FILE = Path("/etc/geno/names")
ANSWER_TEMPLATE = Path("/etc/geno/answer.toml.tpl")
DNSMASQ_HOSTS = Path("/etc/dnsmasq.hosts")

# Load or initialize state
def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "queue": [],  # [(ip, hostname), ...]
        "installing": {},  # {mac: {"ip": "...", "hostname": "...", "timestamp": "..."}}
        "provisioned": {}  # {mac: {"ip": "...", "hostname": "...", "completed": "..."}}
    }

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def update_dnsmasq():
    """Update dnsmasq hosts file and reload."""
    state = load_state()

    lines = []
    # Add entries to ignore provisioned MACs
    for mac, info in state["provisioned"].items():
        lines.append(f"{mac},ignore")

    # Add reservations for installing nodes
    for mac, info in state["installing"].items():
        lines.append(f"{mac},{info['ip']},{info['hostname']}")

    with open(DNSMASQ_HOSTS, 'w') as f:
        f.write('\n'.join(lines))

    # Reload dnsmasq
    os.system("killall -HUP dnsmasq")

# Initialize queue on startup
state = load_state()
if not state["queue"]:
    # Load names and create queue
    with open(NAMES_FILE) as f:
        names = [line.strip() for line in f if line.strip()]

    base_ip = "10.11.0"
    state["queue"] = [(f"{base_ip}.{i+2}", name) for i, name in enumerate(names)]
    save_state(state)

@app.route('/dhcp-script', methods=['POST'])
def dhcp_script():
    """Called by dnsmasq for DHCP events (if using dhcp-script option)."""
    # This endpoint can be used for dynamic DHCP decision-making
    # For now, we rely on dnsmasq.hosts file updates
    pass

@app.route('/answer/<ip>')
def serve_answer(ip):
    """Serve answer file for specific IP."""
    state = load_state()

    # Find the hostname for this IP
    hostname = None
    for mac, info in state["installing"].items():
        if info["ip"] == ip:
            hostname = info["hostname"]
            break

    if not hostname:
        return "Answer file not available", 404

    # Load template and substitute
    with open(ANSWER_TEMPLATE) as f:
        template = f.read()

    # TODO: Get these from secure storage (1Password)
    answer = template.replace("{{ hostname }}", hostname)
    answer = answer.replace("{{ ip }}", ip)
    answer = answer.replace("{{ root_password_hashed }}", "$y$j9T$72Y8qOSgNS.c4VfeamXGx0$l3Ms5HnMRjRRYR6T7tTubjJU/4uBnKMA//GWURm4Bm1")
    answer = answer.replace("{{ ssh_public_key }}", "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7xDRJrfc+bsgZpHmmvDtKhMIlDlJd7OQ1x08UPAHiH")
    # Add other substitutions as needed

    return Response(answer, mimetype='text/plain')

@app.route('/post-proxmox-install', methods=['POST'])
def post_install_webhook():
    """Webhook endpoint called after Proxmox installation completes."""
    # Proxmox sends installation details
    data = request.json or {}

    # Find which MAC completed installation based on IP
    # This requires extracting IP from the webhook data

    state = load_state()
    # Move from installing to provisioned
    # Update dnsmasq to ignore this MAC
    # Return success

    return jsonify({"status": "ok"})

@app.route('/status')
def status():
    """View current provisioning status."""
    state = load_state()
    return jsonify(state)

@app.route('/assign-next/<mac>')
def assign_next(mac):
    """Manually trigger assignment for a specific MAC."""
    state = load_state()

    if mac in state["provisioned"]:
        return jsonify({"error": "MAC already provisioned"}), 400

    if not state["queue"]:
        return jsonify({"error": "No configurations left in queue"}), 400

    # Pop next config from queue
    ip, hostname = state["queue"].pop(0)

    # Add to installing
    state["installing"][mac] = {
        "ip": ip,
        "hostname": hostname,
        "timestamp": datetime.utcnow().isoformat()
    }

    save_state(state)
    update_dnsmasq()

    return jsonify({"mac": mac, "ip": ip, "hostname": hostname})

@app.route('/reset')
def reset():
    """Reset the provisioning state."""
    state = load_state()
    state["queue"] = []
    state["installing"] = {}
    state["provisioned"] = {}
    save_state(state)
    return jsonify({"status": "reset"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOFPYTHON

chmod +x /srv/geno/app.py

# Create systemd-style init scripts for OpenRC (Alpine)

# dnsmasq service
rc-update add dnsmasq default
rc-service dnsmasq start

# nginx service
rc-update add nginx default
rc-service nginx start

# Create init script for geno app
cat > /etc/init.d/geno-app <<'EOFINIT'
#!/sbin/openrc-run

name="geno-app"
command="/usr/bin/python3"
command_args="/srv/geno/app.py"
command_background="yes"
pidfile="/var/run/geno-app.pid"

depend() {
    need net
    after nginx dnsmasq
}
EOFINIT

chmod +x /etc/init.d/geno-app
rc-update add geno-app default
rc-service geno-app start

echo "=== Geno Provisioning Server Setup Complete ==="
echo "Services running:"
echo "  - dnsmasq (DHCP + TFTP) on eth0"
echo "  - nginx (HTTP) on port 80"
echo "  - geno-app (provisioning logic) on port 5000"
echo ""
echo "Status endpoint: http://10.11.0.65/status"
