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