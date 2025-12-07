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
        stack = pulumi.get_stack()
        infra_stack = pulumi.StackReference(f"organization/infra/{stack}")

        self.domain_name = infra_stack.get_output("domain_name")
        self.key_name = infra_stack.get_output("austin_key_pair_name")
        self.zone_id = infra_stack.get_output("domain_zone_id")

        self.user_data = None
        self.instance_request = None
        self.elastic_ip = None

        # Create all resources during initialization
        self._create_resources()
        self.register_outputs()

    def _create_resources(self):
        """Internal method to create all resources. Called from __init__."""
        self.load_config()
        self.create_instance()
        self.create_elastic_ip()

    def load_config(self):
        """Load config, including user data script, from local files"""
        # Try to load config from local file first, then fall back to SSM Parameter Store
        try:
            with open("data/config.json", "r") as f:
                config = f.read()
        except FileNotFoundError:
            # Local file doesn't exist, verify parameter exists in SSM Parameter Store
            try:
                existing_param = aws.ssm.get_parameter(
                    name="/mail-server/config"
                )
                # Store the existing value (encrypted) to use as placeholder during adoption
                existing_parameter_value = existing_param.value
                config = None
            except Exception as e:
                # Parameter doesn't exist in AWS either
                raise Exception(
                    "config.json not found locally and SSM parameter '/mail-server/config' "
                    "does not exist in AWS. Please either:\n"
                    "1. Create data/config.json locally, or\n"
                    "2. Create the SSM parameter: aws ssm put-parameter --name '/mail-server/config' --value file://config.json --type SecureString"
                ) from e

        with open("data/docker-compose.yml", "r") as f:
            docker_compose_yml = f.read()

        # Always manage the SSM parameter, but only update the value if config.json exists locally
        # If config.json doesn't exist, use ignore_changes to prevent overwriting the existing value
        parameter_opts = ResourceOptions(parent=self)
        if config is None:
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
            parameter_value = config

        aws.ssm.Parameter(
            "mail-server-config-parameter",
            name="/mail-server/config",
            type="SecureString",
            value=parameter_value,
            tags={
                "Project": "mail-server"
            },
            opts=parameter_opts
        )

        with open("data/user-data.sh", "r") as f:
            self.user_data = f.read().replace("{{ docker_compose_yml }}", docker_compose_yml)

    def create_instance(self):
        """Request the EC2 instance from AWS
        
        While testing, I'm using a spot instance with a 1 hour expiration.
        """
        expire_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.instance_request = aws.ec2.SpotInstanceRequest(
            "mail_server_instance",
            aws.ec2.SpotInstanceRequestArgs(
                ami=self.get_ami().id,
                instance_type="t3.micro",
                iam_instance_profile=self.get_instance_profile().name,
                vpc_security_group_ids=[self.get_security_group().id],
                key_name=self.key_name,
                tags={
                        "Project": "mail-server",
                        "ExpireAt": expire_at
                },
                user_data_base64=base64.b64encode(self.user_data.encode()).decode(),
                wait_for_fulfillment=True,
            ),
            opts=ResourceOptions(parent=self)
        )

    def create_elastic_ip(self):
        """Create and associate an Elastic IP with the spot instance"""
        # Create the Elastic IP
        self.elastic_ip = aws.ec2.Eip(
            "mail-server-elastic-ip",
            domain="vpc",  # Use VPC domain for instances in a VPC
            tags={
                "Project": "mail-server"
            },
            opts=ResourceOptions(parent=self)
        )

        # Associate the Elastic IP with the spot instance
        aws.ec2.EipAssociation(
            "mail-server-eip-association",
            instance_id=self.instance_request.spot_instance_id,
            allocation_id=self.elastic_ip.id,
            opts=ResourceOptions(parent=self)
        )

        pulumi.export("elastic_ip", self.elastic_ip.public_ip)

        self.domain_name.apply(lambda domain_name: self.create_route53_records(domain_name))

    def create_route53_records(self, domain_name):
        """Create Route 53 records for the mail server"""
        aws.route53.Record(
            "mail-server-record",
            name=f"mail.{domain_name}",
            zone_id=self.zone_id,
            type="A",
            ttl=300,
            records=[self.elastic_ip.public_ip],
            opts=ResourceOptions(parent=self)
        )

    def get_ami(self):
        return aws.ec2.get_ami(
            most_recent=True,
            owners=["amazon"],
            filters=[{
                "name": "name",
                "values": ["al2023-ami-2023.9.20251117.1-kernel-6.1-x86_64"]
            }]
        )
    
    def get_instance_profile(self):
        # IAM role for EC2 instance to access SSM Parameter Store
        instance_role = aws.iam.Role(
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

        pulumi.export("instance_role_arn", instance_role.arn)

        # Attach SSM managed instance core policy (allows SSM access)
        aws.iam.RolePolicyAttachment(
            "mail-server-ssm-core",
            role=instance_role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            opts=ResourceOptions(parent=self)
        )

        # Policy to allow reading from SSM Parameter Store
        ssm_read_policy = aws.iam.RolePolicy(
            "mail-server-ssm-read-policy",
            role=instance_role.id,
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
        return aws.iam.InstanceProfile(
            "mail-server-instance-profile",
            role=instance_role.name,
            opts=ResourceOptions(parent=self)
        )

    def get_security_group(self):
        return aws.ec2.SecurityGroup(
            "mail-server-sg",
            description="Security group for mail server instance",
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="tcp",
                    from_port=22,
                    to_port=22,
                    cidr_blocks=["0.0.0.0/0"],
                    description="Allow SSH"
                ),
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="tcp",
                    from_port=80,
                    to_port=80,
                    cidr_blocks=["0.0.0.0/0"],
                    description="Allow HTTP"
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                    description="Allow all outbound traffic"
                ),
            ],
            tags={
                "Project": "mail-server"
            },
            opts=ResourceOptions(parent=self)
        )

        
    def register_outputs(self):
        # Register outputs
        pulumi.export("ssm_config_path", "/mail-server/config")
        pulumi.export("instance_id", self.instance_request.spot_instance_id)
        pulumi.export("instance_public_ip", self.instance_request.public_ip)

mail_server = MailServer("mail-server")