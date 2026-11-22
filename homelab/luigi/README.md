# Luigi DNS Server

Luigi is my homelab DNS server, managed by Dnsmasq.

It includes DNS caching for my home network, forwarding to Quad9
(`9.9.9.9`, `149.112.112.112`) and answering `lab.rwhq.net` names locally.

## How it's deployed

- `terraform/` creates the Alpine LXC container on Proxmox. The root account
  gets the public half of the services SSH key from 1Password.
- `dnsmasq.d/` is the dnsmasq config. On push to `main`, the `Luigi` workflow:
  1. checks the config with `dnsmasq --test`,
  2. plans and applies Terraform (gated by the `production` environment),
  3. copies `dnsmasq.d/*` to `/etc/dnsmasq.d/` on luigi over the tailnet,
     runs `dnsmasq --test` there, and restarts dnsmasq with `rc-service`.
     If the test fails, the previous config is restored and the job fails.

Only `*.conf` files in `dnsmasq.d/` are read as config. Other files (like
`lab_hosts.hosts`) are pulled in by `addn-hosts`.

## Bootstrap (manual, once per container)

Alpine doesn't ship an SSH server, and CI can't install packages on a fresh
container without a root key on the Proxmox host for `pct exec`. So after
Terraform creates luigi, do this once from the Proxmox host:

```sh
pct enter <luigi vmid>

apk update
apk add openssh dnsmasq

# sshd: key-only root login (Terraform already wrote the services key to
# /root/.ssh/authorized_keys)
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
rc-update add sshd default
rc-service sshd start

# dnsmasq: read only *.conf files from /etc/dnsmasq.d
mkdir -p /etc/dnsmasq.d
grep -qx 'conf-dir=/etc/dnsmasq.d/,\*.conf' /etc/dnsmasq.conf \
  || echo 'conf-dir=/etc/dnsmasq.d/,*.conf' >> /etc/dnsmasq.conf
rc-update add dnsmasq default
rc-service dnsmasq start
```

Then pin luigi's SSH host key for CI. From a machine on the tailnet:

```sh
ssh-keyscan -t ed25519 10.11.0.67
```

Check the fingerprint against the one on luigi
(`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`), then save the
`ssh-keyscan` output as the `LUIGI_KNOWN_HOSTS` repository variable
(Settings → Secrets and variables → Actions → Variables). Redo this whenever
the container is recreated, since it gets a new host key.

## CI requirements

- `OP_SERVICE_ACCOUNT_TOKEN` can read the services SSH key item (the deploy
  job reads its private key with `op read`).
- The tailnet ACL lets `tag:ci` reach `10.11.0.67:22`.
- The `LUIGI_KNOWN_HOSTS` repository variable is set (see above).

## Checking it

```sh
dig @10.11.0.67 luigi.lab.rwhq.net   # 10.11.0.67
dig @10.11.0.67 example.com          # run twice: second answer ~0 ms (cached)
```
