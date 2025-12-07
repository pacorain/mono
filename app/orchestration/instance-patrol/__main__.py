

import inspect
import pulumi
import pulumi_aws as aws
from pulumi import ComponentResource, ResourceOptions

def lambda_handler(event, context):
    import boto3
    from datetime import datetime, timezone

    ec2 = boto3.client('ec2')
    
    # Filter to get all instances with an ExpireAt tag
    reservations = ec2.describe_instances(
        Filters=[
            {'Name': 'tag-key', 'Values': ['ExpireAt']},
            {'Name': 'instance-state-name', 'Values': ['pending', 'running', 'stopping', 'stopped']}
        ]
    ).get('Reservations', [])

    instances_to_terminate = []

    for reservation in reservations:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
            expire_at = tags.get('ExpireAt')
            if expire_at:
                try:
                    expire_time = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
                    if expire_time < datetime.now(timezone.utc):
                        instances_to_terminate.append(instance_id)
                except ValueError:
                    print(f"Invalid timestamp format for instance {instance_id}: {expire_at}")

    if instances_to_terminate:
        print(f"Terminating instances: {instances_to_terminate}")
        ec2.terminate_instances(InstanceIds=instances_to_terminate)
    else:
        print("No instances to terminate.")

class InstancePatrol(ComponentResource):
    def __init__(self, name, opts=None):
        super().__init__("rwhq:orchestration:instance-patrol", name, None, opts)

        # Create IAM role
        self.role = aws.iam.Role(
            "instance-patrol-role",
            assume_role_policy="""{
              "Version": "2012-10-17",
              "Statement": [{
                "Action": "sts:AssumeRole",
                "Principal": {
                  "Service": "lambda.amazonaws.com"
                },
                "Effect": "Allow",
                "Sid": ""
              }]
            }""",
            tags={
                "Project": "orchestration/instance-patrol"
            },
            opts=ResourceOptions(parent=self)
        )

        # Attach basic execution policy
        aws.iam.RolePolicyAttachment(
            "instance-patrol-basic-execution",
            role=self.role.name,
            policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            opts=ResourceOptions(parent=self)
        )

        # Attach EC2 policy
        aws.iam.RolePolicyAttachment(
            "instance-patrol-lambda-ec2",
            role=self.role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonEC2FullAccess",
            opts=ResourceOptions(parent=self)
        )

        # Create Lambda function
        self.function = aws.lambda_.Function(
            "instance-patrol-lambda",
            role=self.role.arn,
            runtime="python3.11",
            handler="index.lambda_handler",
            code=pulumi.AssetArchive({"index.py": pulumi.StringAsset(inspect.getsource(lambda_handler))}),
            timeout=60,
            tags={
                "Project": "orchestration/instance-patrol"
            },
            opts=ResourceOptions(parent=self)
        )

        # Create CloudWatch Event Rule
        self.rule = aws.cloudwatch.EventRule(
            "instance-patrol-schedule-rule",
            schedule_expression="rate(15 minutes)",
            tags={
                "Project": "orchestration/instance-patrol"
            },
            opts=ResourceOptions(parent=self)
        )

        # Grant permission to invoke Lambda
        aws.lambda_.Permission(
            "instance-patrol-lambda-permission",
            action="lambda:InvokeFunction",
            function=self.function.name,
            principal="events.amazonaws.com",
            source_arn=self.rule.arn,
            opts=ResourceOptions(parent=self)
        )

        # Create Event Target
        aws.cloudwatch.EventTarget(
            "instance-patrol-target",
            rule=self.rule.name,
            arn=self.function.arn,
            opts=ResourceOptions(parent=self)
        )

        # Register outputs
        self.register_outputs({
            "function_arn": self.function.arn,
            "function_name": self.function.name,
            "rule_arn": self.rule.arn
        })

# Create the Kamek Lambda component
instance_patrol = InstancePatrol("instance-patrol")
