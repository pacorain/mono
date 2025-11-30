# Pulumi Backend

This is the Pulumi backend for my personal infra.

To avoid recursion, the backend is set up via the AWS console, and then stored in the git repo.

## Setup

To configure pulumi to manage the backend, log into local pulumi (you will need the local pulumi config passphrase):

```bash
pulumi login --local
```

## Use

To switch Pulumi to use the backend, use:

```bash
pulumi login "s3://<bucket-name>/<path>"
```