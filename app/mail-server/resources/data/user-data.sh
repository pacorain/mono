#!/bin/bash
set -euo pipefail

# Install AWS CLI if not present (Amazon Linux 2023 should have it)
if ! command -v aws &> /dev/null; then
    yum update -y
    yum install -y aws-cli
fi

yum install -y jq docker

# Install Docker Compose plugin
DOCKER_CONFIG=${DOCKER_CONFIG:-/root/.docker}
mkdir -p $DOCKER_CONFIG/cli-plugins
curl -SL https://github.com/docker/compose/releases/download/v5.0.0/docker-compose-linux-x86_64 -o $DOCKER_CONFIG/cli-plugins/docker-compose
chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose

# Configuration
SSM_CONFIG_PARAM="/mail-server/config"

# Create directories
mkdir -p /opt/mailu
cd /opt/mailu

export MAILU_DATA_DIR=/opt/mailu

# Fetch configuration JSON from SSM Parameter Store
echo "Fetching configuration from SSM Parameter Store..."
CONFIG_JSON=$(aws ssm get-parameter \
    --name "${SSM_CONFIG_PARAM}" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text)

if [ -z "$CONFIG_JSON" ] || [ "$CONFIG_JSON" == "None" ]; then
    echo "Error: Configuration not found in SSM Parameter Store at ${SSM_CONFIG_PARAM}"
    exit 1
fi

eval $(jq -r '.docker | to_entries[] | "export \(.key)=\(.value)"' <<< "$CONFIG_JSON")

# Get the public IP address from EC2 instance metadata
echo "Fetching public IP address from instance metadata..."
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
if [ -z "$PUBLIC_IP" ]; then
    echo "Warning: Could not retrieve public IP address, falling back to 127.0.0.1"
    export BIND_ADDRESS="127.0.0.1"
else
    echo "Using public IP address: $PUBLIC_IP"
    export BIND_ADDRESS="$PUBLIC_IP"
fi

# TODO: Write .env file
touch /opt/mailu/mailu.env

# Create docker-compose.yml from template with environment variable substitution
cat > docker-compose.yml <<'EOF'
{{ docker_compose_yml }}
EOF

# Start and enable Docker service
systemctl enable docker
systemctl start docker

# Start services with Docker Compose
echo "Starting services with Docker Compose..."
docker compose up -d

echo "User-data script completed successfully"
