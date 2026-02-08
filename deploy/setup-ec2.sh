#!/bin/bash
# EC2 Ubuntu 22.04 setup script for Bloaty McBloatface
# Run as: sudo bash deploy/setup-ec2.sh

set -e

echo "=== Bloaty McBloatface EC2 Setup ==="

# Update system
echo "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install Docker
echo "Installing Docker..."
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add ubuntu user to docker group
usermod -aG docker ubuntu

# Install Certbot
echo "Installing Certbot..."
apt-get install -y certbot

# Install AWS CLI
echo "Installing AWS CLI..."
apt-get install -y awscli jq

# Configure firewall
echo "Configuring firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Create app directory structure
echo "Setting up app directory..."
mkdir -p /opt/bloaty/uploads
chown -R ubuntu:ubuntu /opt/bloaty

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
ExecStart=/usr/bin/docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml down
User=ubuntu
Group=docker

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bloaty.service

# Set up certbot auto-renewal
echo "Configuring SSL auto-renewal..."
cat > /etc/cron.d/certbot-renew << 'EOF'
0 0,12 * * * root certbot renew --quiet --deploy-hook "docker compose -f /opt/bloaty/docker-compose.yml -f /opt/bloaty/deploy/docker-compose.prod.yml exec nginx nginx -s reload"
EOF

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Clone your repo to /opt/bloaty (or copy files)"
echo "2. Run: ./deploy/fetch-secrets.sh"
echo "3. Run: sudo certbot certonly --standalone -d YOUR_DOMAIN"
echo "4. Run: docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d"
echo ""
