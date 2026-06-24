# Secrets injected via 1Password CLI
# Run the following to restore:
# op inject -i secrets.auto.tfvars.tpl -o secrets.auto.tfvars

# State bucket
bucket_name = "{{ op://Homelab/tf-state-bucket/password }}"