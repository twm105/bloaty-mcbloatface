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

# Install jq, git, and cronie (AWS CLI is pre-installed on Amazon Linux)
echo "Installing jq, git, cronie..."
dnf install -y jq git cronie
systemctl enable crond
systemctl start crond

# Create app directory structure
echo "Setting up app directory..."
mkdir -p /opt/bloaty/uploads
mkdir -p /var/www/certbot
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
0 0,12 * * * root certbot renew --quiet --webroot -w /var/www/certbot --deploy-hook "docker compose -f /opt/bloaty/docker-compose.yml -f /opt/bloaty/deploy/docker-compose.prod.yml exec -T nginx nginx -s reload"
EOF

# Set up daily backup cron job
echo "Configuring daily backups..."
cat > /etc/cron.d/bloaty-backup << 'EOF'
0 3 * * * ec2-user /opt/bloaty/deploy/backup.sh >> /var/log/bloaty-backup.log 2>&1
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
echo "5. Reconfigure certbot for webroot renewal (nginx must be running first):"
echo "   sudo certbot reconfigure --cert-name YOUR_DOMAIN --authenticator webroot --webroot-path /var/www/certbot"
echo ""
echo "Automated tasks configured:"
echo "- SSL renewal: twice daily (certbot)"
echo "- Backups to S3: daily at 3am (check /var/log/bloaty-backup.log)"
echo ""
