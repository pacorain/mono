#!/bin/sh
# Check that luigi came back cleanly after a reboot or power loss.
#
# Run from any machine on the tailnet:
#   ./check-boot.sh                 # ssh as root@10.11.0.67
#   ./check-boot.sh luigi           # or any ssh host alias for luigi
#
# Exits non-zero if anything is off. Needs dig and ssh.
set -u

IP=10.11.0.67
TARGET=${1:-root@$IP}
fail=0

ok()  { printf 'ok    %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fail=1; }

# DNS, from the outside: a lab name answered locally, and a public name
# answered through the upstream resolvers.
lab=$(dig +short +time=2 +tries=2 @"$IP" luigi.lab.rwhq.net A)
if [ "$lab" = "$IP" ]; then
  ok "luigi.lab.rwhq.net -> $lab"
else
  bad "luigi.lab.rwhq.net: expected $IP, got '${lab:-no answer}'"
fi

ext=$(dig +short +time=2 +tries=2 @"$IP" example.com A | head -n 1)
if [ -n "$ext" ]; then
  ok "example.com -> $ext (upstream forwarding works)"
else
  bad "example.com: no answer (dnsmasq down, or upstream unreachable)"
fi

# On luigi: are dnsmasq and sshd running now, and will they start on the
# next boot? Alpine uses OpenRC, so "starts on boot" means "is in the
# default runlevel".
ssh -o ConnectTimeout=5 -o BatchMode=yes "$TARGET" '
  f=0
  echo "info  container $(uptime)"
  for svc in dnsmasq sshd; do
    if rc-update show default | grep -qw "$svc"; then
      echo "ok    $svc starts on boot"
    else
      echo "FAIL  $svc is not in the default runlevel (fix: rc-update add $svc default)"
      f=1
    fi
    if rc-service "$svc" status >/dev/null 2>&1; then
      echo "ok    $svc is running"
    else
      echo "FAIL  $svc is not running"
      f=1
    fi
  done
  exit $f
' || fail=1

if [ "$fail" -eq 0 ]; then
  echo "luigi looks healthy"
else
  echo "luigi needs a look" >&2
fi
exit "$fail"
