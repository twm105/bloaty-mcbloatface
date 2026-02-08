#!/bin/bash
# EC2 Amazon Linux 2023 setup script for Bloaty McBloatface
# Run as: sudo bash deploy/setup-ec2.sh

set -e

echo "=== Bloaty McBloatface EC2 Setup ==="

# Update system
echo "Updating system packages..."
dnf update -y

# Install Docker
echo "Installing Docker..."
dnf install -y docker
systemctl start docker
systemctl enable docker

# Install Docker Compose plugin
echo "Installing Docker Compose..."
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m) \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Add ec2-user to docker group
usermod -aG docker ec2-user

# Install Certbot
echo "Installing Certbot..."
dnf install -y certbot

# Install jq (AWS CLI is pre-installed on Amazon Linux)
echo "Installing jq..."
dnf install -y jq git

# Create app directory structure
echo "Setting up app directory..."
mkdir -p /opt/bloaty/uploads
chown -R ec2-user:ec2-user /opt/bloaty

# Create systemd service for docker-compose
echo "Creating systemd service..."
cat > /etc/systemd/system/bloaty.service << 'EOF'
[Unit]
Description=Bloaty McBloatface
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/bloaty
ExecStart=/usr/local/lib/docker/cli-plugins/docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
ExecStop=/usr/local/lib/docker/cli-plugins/docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml down
User=ec2-user
Group=docker

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bloaty.service

# Set up certbot auto-renewal
echo "Configuring SSL auto-renewal..."
cat > /etc/cron.d/certbot-renew << 'EOF'
0 0,12 * * * root certbot renew --quiet --deploy-hook "/usr/local/lib/docker/cli-plugins/docker-compose -f /opt/bloaty/docker-compose.yml -f /opt/bloaty/deploy/docker-compose.prod.yml exec nginx nginx -s reload"
EOF

echo ""
echo "=== Setup Complete ==="
echo ""
echo "IMPORTANT: Log out and back in for docker group to take effect"
echo ""
echo "Next steps:"
echo "1. Clone your repo to /opt/bloaty (or copy files)"
echo "2. Run: cd /opt/bloaty && ./deploy/fetch-secrets.sh"
echo "3. Run: sudo certbot certonly --standalone -d YOUR_DOMAIN"
echo "4. Run: docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d"
echo ""
