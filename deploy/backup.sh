#!/bin/bash
# Daily backup script for Bloaty McBloatface
# Backs up PostgreSQL database and uploads to S3
# Add to cron: 0 3 * * * /opt/bloaty/deploy/backup.sh >> /var/log/bloaty-backup.log 2>&1

set -e

# Configuration
APP_DIR="/opt/bloaty"
BACKUP_DIR="/opt/bloaty/backups"
S3_BUCKET="${BACKUP_S3_BUCKET:-bloaty-backups-XXXXX}"
REGION="${AWS_REGION:-eu-north-1}"
DATE=$(date +%Y-%m-%d)
RETENTION_DAYS=7

echo "=== Bloaty Backup: $DATE ==="

# Create backup directory if needed
mkdir -p "$BACKUP_DIR"

# Database backup
echo "Backing up database..."
DB_BACKUP="$BACKUP_DIR/bloaty-$DATE.sql.gz"

docker compose -f "$APP_DIR/docker-compose.yml" -f "$APP_DIR/deploy/docker-compose.prod.yml" \
    exec -T db pg_dump -U postgres bloaty | gzip > "$DB_BACKUP"

echo "Database backup created: $DB_BACKUP ($(du -h "$DB_BACKUP" | cut -f1))"

# Upload database backup to S3
echo "Uploading database backup to S3..."
aws s3 cp "$DB_BACKUP" "s3://$S3_BUCKET/db/bloaty-$DATE.sql.gz" \
    --region "$REGION"

# Sync uploads folder to S3
echo "Syncing uploads to S3..."
aws s3 sync "$APP_DIR/uploads/" "s3://$S3_BUCKET/uploads/" \
    --region "$REGION" \
    --delete

# Clean up old local backups
echo "Cleaning up local backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "bloaty-*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "=== Backup complete ==="
