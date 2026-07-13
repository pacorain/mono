#!/bin/sh
# One-time provisioning of the luigi DNS node (Alpine LXC).
#
# Run as root by the Terraform provisioner (homelab/luigi/terraform/bootstrap.tf),
# which first uploads:
#   /tmp/luigi-dns-sync           the sync script
#   /tmp/luigi-dns-aws.env        S3 read credentials + sync settings
#   /tmp/luigi-dns-webhook-token  bearer token for the webhook listener
#
# Installs dnsmasq + the webhook listener + the hourly cron fallback, then
# runs the first sync so a fresh node comes up with the latest published
# config. Idempotent: safe to re-run when the scripts change.
set -eu

# The webhook package lives in the community repository
sed -i -e 's|^#\(.*/community\)$|\1|' /etc/apk/repositories
apk update
apk add dnsmasq curl ca-certificates webhook

mkdir -p /etc/luigi-dns /etc/dnsmasq.d /var/lib/luigi-dns /etc/webhook

install -m 0755 /tmp/luigi-dns-sync /usr/local/bin/luigi-dns-sync
install -m 0600 /tmp/luigi-dns-aws.env /etc/luigi-dns/aws.env
rm -f /tmp/luigi-dns-sync /tmp/luigi-dns-aws.env

# Everything dnsmasq serves comes from the synced conf-dir
cat > /etc/dnsmasq.conf <<'EOF'
# Managed by luigi-dns bootstrap; config is synced into /etc/dnsmasq.d/
conf-dir=/etc/dnsmasq.d/,*.conf
EOF

# Webhook listener: a POST with the right bearer token triggers a sync.
# The request carries no config data; the sync always reads S3 itself.
WEBHOOK_TOKEN=$(cat /tmp/luigi-dns-webhook-token)
rm -f /tmp/luigi-dns-webhook-token
cat > /etc/webhook/hooks.json <<EOF
[
  {
    "id": "dns-sync",
    "execute-command": "/usr/local/bin/luigi-dns-sync",
    "command-working-directory": "/",
    "include-command-output-in-response": true,
    "trigger-rule": {
      "match": {
        "type": "value",
        "value": "Bearer ${WEBHOOK_TOKEN}",
        "parameter": { "source": "header", "name": "Authorization" }
      }
    }
  }
]
EOF
chmod 0600 /etc/webhook/hooks.json

cat > /etc/init.d/luigi-webhook <<'EOF'
#!/sbin/openrc-run
name="luigi-webhook"
description="Webhook listener that triggers luigi-dns-sync"
command="/usr/bin/webhook"
command_args="-hooks /etc/webhook/hooks.json -ip 0.0.0.0 -port 9000 -nopanic"
command_background=true
pidfile="/run/luigi-webhook.pid"

depend() {
    need net
}
EOF
chmod 0755 /etc/init.d/luigi-webhook

# Hourly fallback for missed webhooks (Alpine's default root crontab runs
# /etc/periodic/hourly via run-parts)
ln -sf /usr/local/bin/luigi-dns-sync /etc/periodic/hourly/luigi-dns-sync

rc-update add dnsmasq default 2>/dev/null || true
rc-update add crond default 2>/dev/null || true
rc-update add luigi-webhook default 2>/dev/null || true
rc-service crond start 2>/dev/null || true
rc-service luigi-webhook restart

# First sync: pulls the latest published config and (re)starts dnsmasq.
# Tolerate failure so provisioning a node before the first CI publish still
# succeeds; the hourly cron picks it up once an artifact exists.
if ! /usr/local/bin/luigi-dns-sync; then
  echo "warning: initial sync failed (nothing published yet?); cron will retry hourly" >&2
fi

echo "bootstrap complete"
