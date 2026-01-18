#!/bin/sh
set -e

echo "=== Geno Provisioning Server Setup ==="

# Add proxmox repository
wget https://enterprise.proxmox.com/debian/proxmox-archive-keyring-trixie.gpg -qO /etc/apt/trusted.gpg.d/proxmox-archive-keyring-trixie.gpg
echo "deb http://download.proxmox.com/debian/pve trixie pve-no-subscription" > /etc/apt/sources.list.d/proxmox.list

# Update package repository
apt update

# Install required packages
apt install -y \
    dnsmasq \
    nginx \
    python3 \
    python3-flask \
    wget \
    zstd \
    cpio \
    xorriso \
    proxmox-auto-install-assistant

# Create directories
mkdir -p /srv/http/answers
mkdir -p /srv/geno/state
mkdir -p /etc/geno

# Configure dnsmasq for DHCP
cat > /etc/dnsmasq.conf <<'EOF'
# Interface binding
interface=eth0
bind-interfaces

# DHCP configuration
# Temporary IPs for initial lease - Flask app assigns permanent IPs
dhcp-range=10.11.0.7,10.11.0.15,255.255.252.0,12h

# Gateway
dhcp-option=3,10.11.0.1

# DNS servers
dhcp-option=6,8.8.8.8,1.1.1.1

# Proxmox answer file URL (option 250)
dhcp-option=250,http://10.11.0.65/answer

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
cat > /etc/nginx/sites-available/geno.conf <<'EOF'
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

ln -sf /etc/nginx/sites-available/geno.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Copy answer file template to geno directory
cat > /etc/geno/answer.toml.tpl <<'EOFTEMPLATE'
[global]
keyboard = "en-us"
country = "us"
fqdn = "{{ hostname }}.rwhq.net"
timezone = "America/New_York"
mailto = "austin@rainwater.family"
root-password-hashed = "{{ root_password_hashed }}"
root-ssh-keys = ["{{ ssh_public_key }}"]
reboot-on-error = false

[network]
source = "from-answer"
cidr = "{{ ip }}/22"
dns = "8.8.8.8"
gateway = "10.11.0.1"
filter.INTERFACE = "e*"

[disk-setup]
filesystem = "ext4"
disk-list = ["nvme0n1"]

[post-installation-webhook]
url = "http://10.11.0.65/post-proxmox-install"
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
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

STATE_FILE = Path("/srv/geno/state/state.json")
NAMES_FILE = Path("/etc/geno/names")
ANSWER_TEMPLATE = Path("/etc/geno/answer.toml.tpl")

# Load or initialize state
def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "queue": [],  # [(ip, hostname), ...]
        "installing": {},  # {temp_ip: {"ip": "...", "hostname": "...", "timestamp": "..."}}
        "provisioned": {}  # {permanent_ip: {"ip": "...", "hostname": "...", "temp_ip": "...", "completed": "..."}}
    }

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

# Initialize queue on startup
state = load_state()
if not state["queue"]:
    # Load names and create queue
    with open(NAMES_FILE) as f:
        names = [line.strip() for line in f if line.strip()]

    base_ip = "10.11.0"
    state["queue"] = [(f"{base_ip}.{i+2}", name) for i, name in enumerate(names)]
    save_state(state)

@app.route('/answer', methods=['GET', 'POST'])
def serve_answer():
    """Serve answer file based on requesting IP. Assigns config on first request."""
    state = load_state()

    requesting_ip = request.headers.get('X-Real-IP', request.remote_addr)

    # Check if this IP already has a config assigned
    config = None
    for temp_ip, info in state["installing"].items():
        if temp_ip == requesting_ip:
            config = info
            break

    # If not found, assign next config from queue
    if not config:
        if not state["queue"]:
            app.logger.warning(f"No configs left in queue for IP: {requesting_ip}")
            return "No configurations available", 503

        # Pop next config from queue
        permanent_ip, hostname = state["queue"].pop(0)

        config = {
            "ip": permanent_ip,
            "hostname": hostname,
            "status": "installing",
            "timestamp": datetime.utcnow().isoformat()
        }

        # Key by temp_ip instead of MAC (we don't have MAC here)
        state["installing"][requesting_ip] = config
        save_state(state)

        app.logger.info(f"Assigned {hostname} ({permanent_ip}) to temp IP {requesting_ip}")

    # Load template and substitute
    with open(ANSWER_TEMPLATE) as f:
        template = f.read()

    # Use the permanent IP and hostname in the answer file
    answer = template.replace("{{ hostname }}", config["hostname"])
    answer = answer.replace("{{ ip }}", config["ip"])
    answer = answer.replace("{{ root_password_hashed }}", "$y$j9T$72Y8qOSgNS.c4VfeamXGx0$l3Ms5HnMRjRRYR6T7tTubjJU/4uBnKMA//GWURm4Bm1")
    answer = answer.replace("{{ ssh_public_key }}", "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7xDRJrfc+bsgZpHmmvDtKhMIlDlJd7OQ1x08UPAHiH")

    return Response(answer, mimetype='text/plain')

@app.route('/post-proxmox-install', methods=['POST'])
def post_install_webhook():
    """Webhook endpoint called after Proxmox installation completes."""
    state = load_state()

    # The request comes from the newly installed node using its permanent IP
    requesting_ip = request.headers.get('X-Real-IP', request.remote_addr)

    # Find which temp_ip entry has this permanent IP
    completed_temp_ip = None
    for temp_ip, info in state["installing"].items():
        if info["ip"] == requesting_ip:
            completed_temp_ip = temp_ip
            break

    if not completed_temp_ip:
        app.logger.warning(f"Post-install webhook from unknown IP: {requesting_ip}")
        return jsonify({"error": "Unknown source IP"}), 404

    # Move from installing to provisioned (keyed by permanent IP now)
    info = state["installing"].pop(completed_temp_ip)
    state["provisioned"][requesting_ip] = {
        "ip": info["ip"],
        "hostname": info["hostname"],
        "temp_ip": completed_temp_ip,
        "completed": datetime.utcnow().isoformat()
    }

    save_state(state)

    app.logger.info(f"Provisioning complete: {info['hostname']} ({info['ip']})")

    return jsonify({"status": "ok", "hostname": info["hostname"]})

@app.route('/status')
def status():
    """View current provisioning status."""
    state = load_state()
    return jsonify(state)

@app.route('/assign-next/<temp_ip>')
def assign_next(temp_ip):
    """Manually trigger assignment for a specific temp IP."""
    state = load_state()

    if temp_ip in state["installing"]:
        return jsonify({"error": "IP already installing", "info": state["installing"][temp_ip]}), 400

    if not state["queue"]:
        return jsonify({"error": "No configurations left in queue"}), 400

    # Pop next config from queue
    ip, hostname = state["queue"].pop(0)

    # Add to installing
    state["installing"][temp_ip] = {
        "ip": ip,
        "hostname": hostname,
        "status": "installing",
        "timestamp": datetime.utcnow().isoformat()
    }

    save_state(state)

    return jsonify({"temp_ip": temp_ip, "ip": ip, "hostname": hostname})

@app.route('/reset', methods=['POST'])
def reset():
    """Reset the provisioning state and reinitialize the queue."""
    # Reload names and recreate queue
    with open(NAMES_FILE) as f:
        names = [line.strip() for line in f if line.strip()]

    base_ip = "10.11.0"
    state = {
        "queue": [(f"{base_ip}.{i+2}", name) for i, name in enumerate(names)],
        "installing": {},
        "provisioned": {}
    }
    save_state(state)
    update_dnsmasq()

    return jsonify({"status": "reset", "queue_size": len(state["queue"])})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOFPYTHON

chmod +x /srv/geno/app.py

# Start services

# dnsmasq service
systemctl restart dnsmasq || true

# nginx service
systemctl restart nginx || true

# Create systemd service for geno app
cat > /etc/systemd/system/geno-app.service <<'EOF'
[Unit]
Description=Geno App
After=network.target nginx.service dnsmasq.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /srv/geno/app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable geno-app
systemctl restart geno-app || true

echo "=== Geno Provisioning Server Setup Complete ==="
echo "Services running:"
echo "  - dnsmasq (DHCP + TFTP) on eth0"
echo "  - nginx (HTTP) on port 80"
echo "  - geno-app (provisioning logic) on port 5000"
echo ""
echo "Status endpoint: http://10.11.0.65/status"
