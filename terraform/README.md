# Terraform

I've decided to migrate to Terraform for IaC. 

## Secrets

Secrets are stored in 1Password, and injected via the 1Password CLI to gitignored files.

To restore secrets, run `op inject`. e.g.:

```bash
op inject -i secrets.auto.tfvars.tpl -o secrets.auto.tfvars
```

## State Bootstrap

State for most resources is stored in S3. The exception is the bucket itself, which is stored locally.

The terraform configuration is stored in [bootstrap](./bootstrap).