"""An AWS Python Pulumi program"""

from pulumi import ComponentResource, ResourceOptions
import pulumi
import pulumi_aws as aws
from datetime import datetime, timezone, timedelta
import base64
import json


class MailServer(ComponentResource):
    def __init__(self, name, opts=None):
        super().__init__("rwhq:mail-server", name, None, opts)

        # IAM role for EC2 instance to access SSM Parameter Store
        self.instance_role = aws.iam.Role(
            "mail-server-instance-role",
            assume_role_policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }),
            tags={
                "Project": "mail-server"
            },
            opts=ResourceOptions(parent=self)
        )

        # Attach SSM managed instance core policy (allows SSM access)
        aws.iam.RolePolicyAttachment(
            "mail-server-ssm-core",
            role=self.instance_role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            opts=ResourceOptions(parent=self)
        )

        # Policy to allow reading from SSM Parameter Store
        self.ssm_read_policy = aws.iam.RolePolicy(
            "mail-server-ssm-read-policy",
            role=self.instance_role.id,
            policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "ssm:GetParameter",
                        "ssm:GetParameters",
                        "ssm:GetParametersByPath"
                    ],
                    "Resource": f"arn:aws:ssm:*:*:parameter/mail-server/*"
                }]
            }),
            opts=ResourceOptions(parent=self)
        )

        # Create instance profile for the role
        self.instance_profile = aws.iam.InstanceProfile(
            "mail-server-instance-profile",
            role=self.instance_role.name,
            opts=ResourceOptions(parent=self)
        )

        self.ami = aws.ec2.get_ami(
            most_recent=True,
            owners=["amazon"],
            filters=[{
                "name": "name",
                "values": ["al2023-ami-2023.9.20251117.1-kernel-6.1-x86_64"]
            }]
        )

        # Try to load config from local file first, then fall back to SSM Parameter Store
        try:
            with open("data/config.json", "r") as f:
                self.config = f.read()
        except FileNotFoundError:
            # Local file doesn't exist, verify parameter exists in SSM Parameter Store
            try:
                existing_param = aws.ssm.get_parameter(
                    name="/mail-server/config"
                )
                # Store the existing value (encrypted) to use as placeholder during adoption
                existing_parameter_value = existing_param.value
                self.config = None
            except Exception as e:
                # Parameter doesn't exist in AWS either
                raise Exception(
                    "config.json not found locally and SSM parameter '/mail-server/config' "
                    "does not exist in AWS. Please either:\n"
                    "1. Create data/config.json locally, or\n"
                    "2. Create the SSM parameter: aws ssm put-parameter --name '/mail-server/config' --value file://config.json --type SecureString"
                ) from e

        with open("data/docker-compose.yml", "r") as f:
            self.docker_compose_yml = f.read()

        with open("data/user-data.sh", "r") as f:
            self.user_data = f.read().replace("{{ docker_compose_yml }}", self.docker_compose_yml)

        # Always manage the SSM parameter, but only update the value if config.json exists locally
        # If config.json doesn't exist, use ignore_changes to prevent overwriting the existing value
        parameter_opts = ResourceOptions(parent=self)
        if self.config is None:
            # Don't update the value if config.json doesn't exist locally
            parameter_opts = ResourceOptions(
                parent=self,
                ignore_changes=["value"]
            )
            # Use the existing parameter value (encrypted) as placeholder to ensure proper adoption
            # If this is a new parameter, this will be None and we'll use empty JSON
            parameter_value = existing_parameter_value if existing_parameter_value else "{}"
        else:
            # Update the value with the local config
            parameter_value = self.config

        self.config_parameter = aws.ssm.Parameter(
            "mail-server-config-parameter",
            name="/mail-server/config",
            type="SecureString",
            value=parameter_value,
            tags={
                "Project": "mail-server"
            },
            opts=parameter_opts
        )

        # While testing, create a spot EC2 instance
        self.instance = aws.ec2.SpotInstanceRequest(
            "mail_server_instance",
            aws.ec2.SpotInstanceRequestArgs(
                ami=self.ami.id,
                instance_type="t3.micro",
                iam_instance_profile=self.instance_profile.name,
                tags={
                    "Project": "mail-server",
                    "ExpireAt": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
                },
                user_data_base64=base64.b64encode(self.user_data.encode()).decode()
            ),
            opts=ResourceOptions(parent=self)
        )

        # Register outputs
        self.register_outputs({
            "instance_role_arn": self.instance_role.arn,
            "ssm_config_path": "/mail-server/config",
            "instance_id": self.instance.spot_instance_id,
            "instance_public_ip": self.instance.public_ip,
        })

mail_server = MailServer("mail-server")