# Luigi DNS Server

Luigi is my homelab DNS server, managed by Dnsmasq.

It includes DNS caching for my home network.

## Bootstrap

Because Luigi is run on Alpine, there are some bootstrap steps are required before the config can be managed by this repo. Alpine does not come with an SSH server, so management is not possible yet.

```sh
apk update
apk add openssh
```

## Config

The configuration files for Luigi are located in the `config` directory.

The configuration files are deployed via CI/CD.