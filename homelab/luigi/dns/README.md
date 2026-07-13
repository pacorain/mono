# luigi DNS config

dnsmasq configuration for [luigi](../terraform/), the homelab DNS server,
delivered by CI/CD. Edit the files under `dnsmasq.d/` (and `blocklists.txt`),
open a PR, merge — luigi picks up the change within about a minute.

## How it works

```
PR / push to main / weekly cron
        │
        ▼
[build job]   scripts/build.sh → static confs + downloaded blocklists,
              validated with `dnsmasq --test` (PRs get a sticky comment)
        │  (push/schedule only)
        ▼
[publish job] tarball → s3://<artifacts>/lab/luigi/dns/builds/<ts>-<sha>/
              pointer → s3://<artifacts>/lab/luigi/dns/latest
              then POSTs luigi's webhook over the tailnet (best effort)
        │
        ▼
[luigi]       webhook (or hourly cron, or bootstrap) runs luigi-dns-sync:
              reads `latest`, verifies the path is under the trusted prefix
              and the sha256 matches, `dnsmasq --test`, atomic swap of
              /etc/dnsmasq.d, restart, self-check, rollback on failure
```

Design properties:

- **A fresh node configures itself.** The Terraform bootstrap provisioner
  (`../terraform/bootstrap.tf`) installs dnsmasq, the sync script, the webhook
  listener, and the hourly cron, then runs the first sync against S3. No CI
  coordination needed; recreating the container re-runs it automatically.
- **Nothing is exposed to the public internet.** The node only makes outbound
  HTTPS calls to S3. The webhook listens on the LAN and is reached by CI over
  the existing Tailscale subnet router; it requires a bearer token, and even a
  spoofed request only triggers a pull — the request body is ignored and the
  node always fetches the `latest` pointer from S3 itself.
- **Least privilege.** The node holds an IAM key that can only `GetObject` on
  `lab/luigi/dns/*` in the artifacts bucket (which contains nothing else
  sensitive — deliberately not the state bucket). CI's publish role can only
  `PutObject` on the same prefix and is assumable only from `main`.
- **Blocklists** (`blocklists.txt`) are fetched and sanity-checked at build
  time — default is [hagezi Multi LIGHT](https://github.com/hagezi/dns-blocklists)
  in native dnsmasq format — and refreshed by the weekly scheduled run.

## Layout

| Path | Purpose |
|---|---|
| `dnsmasq.d/00-base.conf` | Core dnsmasq settings (upstreams, listen addresses, cache) |
| `dnsmasq.d/10-local-records.conf` | Homelab records under `home.arpa` — add yours here |
| `blocklists.txt` | Public blocklist sources (`<name> <format> <url>`) |
| `scripts/build.sh` | CI: assemble + sanity-check the config artifact |
| `scripts/luigi-dns-sync` | Node: pull/verify/validate/swap/restart (webhook + cron + bootstrap) |
| `scripts/bootstrap.sh` | Node: one-time provisioning, run by the Terraform provisioner |

## One-time setup

1. **1Password** (Homelab vault): create `luigi-dns-artifacts-bucket` with the
   bucket name in the `password` field (same convention as `tf-state-bucket`).
2. **Bootstrap Terraform** (local, like the state bucket):
   `cd terraform/bootstrap && op inject -i secrets.auto.tfvars.tpl -o secrets.auto.tfvars && terraform apply`
   — creates the artifacts bucket and the `github-actions-luigi-dns-publish`
   role, and extends the plan/apply roles so they can manage the node's IAM user.
3. **GitHub repo settings**: variable `DNS_PUBLISH_ROLE_ARN` (from the
   `dns_publish_role_arn` output) and secret `DNS_ARTIFACTS_BUCKET` (the bucket
   name).
4. **Apply luigi Terraform** (merge to main; the existing Luigi workflow does
   it): creates the `luigi-dns-reader` IAM user + webhook token and runs the
   bootstrap provisioner on the node.
5. Merge a change under `homelab/luigi/dns/` (or run the Luigi DNS workflow
   manually) to publish the first artifact.

Requirements on the node side: the Alpine template must have an SSH server for
the provisioner (`file`/`remote-exec` over SSH as root with the services key),
and the `tag:ci` Tailscale ACLs must allow reaching 10.11.0.67 (SSH for the
provisioner, port 9000 for the webhook).

## Verifying a deploy

From a machine on the LAN/tailnet:

```sh
dig @10.11.0.67 luigi.home.arpa    # local record
dig @10.11.0.67 doubleclick.net    # blocked → NXDOMAIN
dig @10.11.0.67 example.com        # normal upstream resolution
```

On the node: `cat /var/lib/luigi-dns/state` shows the deployed build (git sha,
build time, blocklist size); sync activity is logged to syslog with the tag
`luigi-dns-sync`. The previous config is kept at `/etc/dnsmasq.d.last-good`
and restored automatically if a new config fails validation or the
post-restart self-check.
