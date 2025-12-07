import pulumi_aws as aws
import pulumi

config = pulumi.Config()
ssh_key_value = config.get_secret("austin_ssh_key")
domain_name = config.get("domain_name")

# IAM SSH Key for EC2 Instance Connect (temporary SSH access via AWS console/CLI)
austin_ssh_key = aws.ec2.KeyPair(
    "austin-ssh-key",
    key_name="austin-key",
    public_key=ssh_key_value,
    tags={
        "Project": "infra",
        "Name": "austin-key",
    }
)


pulumi.export("austin_key_pair_name", austin_ssh_key.key_name)


net = aws.route53.Zone(
    "main-net-domain-zone",
    name=domain_name,
    tags={
        "Project": "infra",
        "Name": domain_name,
    }
)

pulumi.export("domain_zone_id", net.zone_id)
pulumi.export("domain_name", domain_name)