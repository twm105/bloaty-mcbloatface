# DevOps & Deployment Guide

This document describes how to deploy Bloaty McBloatface to AWS. The deployment uses a single EC2 instance running Docker Compose, with supporting AWS services for DNS, secrets, and backups.

## Architecture Overview

```
Internet → Route 53 → EC2 (t3.small)
                         ├── nginx (:443/:80) ← Let's Encrypt cert
                         ├── web (FastAPI :8000)
                         ├── worker (Dramatiq)
                         ├── PostgreSQL
                         └── Redis

                      EBS Volume (persistent data)

Daily backup → S3 bucket (pg_dump + uploads)
```

**Estimated monthly cost**: ~$20-25
- EC2 t3.small: ~$15
- EBS (20GB gp3): ~$2
- Route 53 hosted zone: ~$0.50
- S3 backup storage: ~$0.50
- Domain registration: ~$12/year (~$1/month)

## Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ VPC (default)                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Public Subnet                                        │   │
│  │  ┌─────────────────────────────────────────────┐    │   │
│  │  │ EC2 (t3.small)                              │    │   │
│  │  │  - IAM Role: bloaty-ec2-role                │    │   │
│  │  │  - Security Group: 22, 80, 443 only         │    │   │
│  │  └─────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
   ┌──────────┐      ┌──────────┐      ┌──────────┐
   │ Secrets  │      │ S3       │      │ Route 53 │
   │ Manager  │      │ Backups  │      │          │
   │          │      │ (SSE-S3) │      │          │
   └──────────┘      └──────────┘      └──────────┘
```

### IAM Role: `bloaty-ec2-role`

Attached to EC2 instance. Grants minimal permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SecretsManagerRead",
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:*:*:secret:bloaty/*"
    },
    {
      "Sid": "S3BackupWrite",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::bloaty-backups-XXXXX/*"
    }
  ]
}
```

**Note**: No S3 read permission - EC2 can write backups but not download them (limits blast radius if compromised).

### S3 Bucket Security

- **Block public access**: All 4 settings ON (default)
- **Bucket policy**: Deny all except bloaty-ec2-role (write) and your IAM user (read)
- **Encryption**: SSE-S3 (AWS-managed keys, automatic)
- **Versioning**: ON (recover from accidental overwrites)
- **Lifecycle**: Delete backups older than 90 days
- **Access logging**: Optional, enables audit trail

### Security Group: `bloaty-sg`

```
Inbound:
  - 22/tcp from YOUR_IP/32 (SSH - restrict to your IP)
  - 80/tcp from 0.0.0.0/0 (HTTP → redirects to HTTPS)
  - 443/tcp from 0.0.0.0/0 (HTTPS)

Outbound:
  - All (needed for apt, Docker Hub, Claude API, AWS APIs)
```

### Secrets Manager

- Secret name: `bloaty/production`
- EC2 fetches once at startup → writes to `.env`
- Secrets never in git, never in Docker image

### Why SSE-S3 is Sufficient (vs KMS)

- IAM controls who can access the bucket (primary protection)
- SSE-S3 encrypts at rest (protects against disk theft at AWS)
- KMS would add audit logs + separate key policy, but:
  - Adds complexity ($1/mo + key management)
  - Doesn't protect if your AWS creds leak (attacker has IAM access)
  - Overkill for single-user personal app
- **Upgrade path**: Can switch to SSE-KMS later without re-uploading data

---

## AWS Setup Steps

### Phase 1: Infrastructure Setup

#### 1. Register Domain (Route 53)

1. Go to Route 53 → Registered domains → Register domain
2. Search for your domain (e.g., `bloaty.com`)
3. Complete registration (~$12/year for .com)
4. Wait for registration to complete (can take 15-30 min)

#### 2. Create Security Group

1. Go to EC2 → Security Groups → Create security group
2. Name: `bloaty-sg`
3. VPC: default
4. Inbound rules:
   - Type: SSH, Source: My IP
   - Type: HTTP, Source: Anywhere-IPv4
   - Type: HTTPS, Source: Anywhere-IPv4
5. Outbound rules: Leave default (all traffic)

#### 3. Create IAM Role

1. Go to IAM → Roles → Create role
2. Trusted entity: AWS service → EC2
3. Skip adding policies (we'll add inline)
4. Name: `bloaty-ec2-role`
5. After creation, click the role → Add permissions → Create inline policy
6. JSON tab, paste:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SecretsManagerRead",
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:*:*:secret:bloaty/*"
    },
    {
      "Sid": "S3BackupWrite",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::bloaty-backups-XXXXX",
        "arn:aws:s3:::bloaty-backups-XXXXX/*"
      ]
    }
  ]
}
```
7. Name: `bloaty-ec2-policy`

#### 4. Create EC2 Instance

1. Go to EC2 → Launch instance
2. Name: `bloaty-prod`
3. AMI: Amazon Linux 2023 (64-bit x86)
4. Instance type: t3.small
5. Key pair: Create new or select existing (save .pem to `~/.ssh/`, chmod 600)
6. Network settings:
   - VPC: default
   - Auto-assign public IP: Enable
   - Security group: Select existing → `bloaty-sg`
7. Storage: 20 GiB gp3
8. Advanced details:
   - IAM instance profile: `bloaty-ec2-role`
9. Launch instance

#### 5. Allocate Elastic IP

1. Go to EC2 → Elastic IPs → Allocate Elastic IP address
2. Allocate
3. Select the new IP → Actions → Associate Elastic IP address
4. Instance: Select `bloaty-prod`
5. Associate

#### 6. Create Route 53 DNS Record

1. Go to Route 53 → Hosted zones → your domain
2. Create record:
   - Record name: (leave blank for root, or `app` for subdomain)
   - Record type: A
   - Value: Your Elastic IP
   - TTL: 300
3. Create record

#### 7. Create S3 Bucket

1. Go to S3 → Create bucket
2. Name: `bloaty-backups-XXXXX` (add random suffix for uniqueness)
3. Region: Same as EC2
4. Block all public access: ON (default)
5. Bucket Versioning: Enable
6. Default encryption: SSE-S3
7. Create bucket
8. After creation, go to Management tab → Create lifecycle rule:
   - Name: `delete-old-backups`
   - Apply to all objects
   - Lifecycle rule actions: Expire current versions
   - Days after object creation: 90

#### 8. Create Secrets Manager Secret

1. Go to Secrets Manager → Store a new secret
2. Secret type: Other type of secret
3. Key/value pairs:
   - `ANTHROPIC_API_KEY`: your Anthropic API key
   - `SESSION_SECRET_KEY`: (generate with `openssl rand -hex 32`)
   - `POSTGRES_PASSWORD`: (generate with `openssl rand -base64 24`)
   - `BACKUP_S3_BUCKET`: your bucket name from step 7 (e.g., `bloaty-backups-XXXXX`)
4. Secret name: `bloaty/production`
5. No rotation
6. Store secret

---

### Phase 2: Server Setup

SSH to your instance:
```bash
ssh -i ~/.ssh/your-key.pem ec2-user@YOUR_ELASTIC_IP
```

Run the setup script:
```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/bloaty-mcbloatface.git /opt/bloaty
cd /opt/bloaty

# Run setup (installs Docker, etc.)
sudo bash deploy/setup-ec2.sh

# Fetch secrets from AWS and create .env
./deploy/fetch-secrets.sh

# Get SSL certificate
sudo certbot certonly --standalone -d YOUR_DOMAIN --non-interactive --agree-tos -m YOUR_EMAIL

# Start services
docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
```

---

### Phase 3: Automation

Both daily backups and SSL certificate renewal are configured automatically by `setup-ec2.sh`:

- **Daily backups**: 3 AM via `/etc/cron.d/bloaty-backup` → logs to `/var/log/bloaty-backup.log`
- **SSL renewal**: Twice daily via `/etc/cron.d/certbot-renew`

Verify cron jobs:
```bash
cat /etc/cron.d/bloaty-backup
cat /etc/cron.d/certbot-renew
```

Test backup manually:
```bash
/opt/bloaty/deploy/backup.sh
```

Test SSL renewal:
```bash
sudo certbot renew --dry-run
```

---

## Configuration Reference

### Environment Variables

| Variable | Dev | Production |
|----------|-----|------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@db:5432/bloaty` | `postgresql://postgres:STRONG_PASSWORD@db:5432/bloaty` |
| `ANTHROPIC_API_KEY` | From local `.env` | From Secrets Manager |
| `REDIS_URL` | `redis://redis:6379/0` | Same |
| `SESSION_SECRET_KEY` | Empty (insecure) | 64-char hex from Secrets Manager |
| `SESSION_COOKIE_SECURE` | `false` | `true` |

### Secrets Manager Structure

Secret name: `bloaty/production`
```json
{
  "ANTHROPIC_API_KEY": "sk-ant-...",
  "SESSION_SECRET_KEY": "64-char-hex-string",
  "POSTGRES_PASSWORD": "strong-random-password",
  "BACKUP_S3_BUCKET": "bloaty-backups-XXXXX"
}
```

---

## Deployment Workflow

### Updating Code

```bash
ssh ec2-user@YOUR_DOMAIN
cd /opt/bloaty
git pull
docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml build
docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
```

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web

# Nginx access logs
docker-compose exec nginx tail -f /var/log/nginx/access.log
```

### Restarting Services

```bash
docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml restart
```

---

## Verification Checklist

1. **DNS**: `dig YOUR_DOMAIN` returns Elastic IP
2. **SSL**: `curl -I https://YOUR_DOMAIN` returns 200 with valid cert
3. **Health**: `curl https://YOUR_DOMAIN/health` returns `{"status":"healthy"}`
4. **App**: Login and test meal upload, symptom logging, diagnosis
5. **Backup**: Check S3 bucket for daily dump files after first backup runs
6. **Logs**: `docker-compose logs` shows no errors

---

## Rollback Plan

### Code Rollback

```bash
cd /opt/bloaty
git log --oneline -5  # Find previous good commit
git checkout COMMIT_HASH
docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml build
docker-compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
```

### Data Restore from Backup

```bash
# Download backup from S3 (from your local machine with read access)
aws s3 cp s3://bloaty-backups-XXXXX/db/bloaty-2024-01-15.sql.gz ./

# Copy to server
scp bloaty-2024-01-15.sql.gz ec2-user@YOUR_DOMAIN:/tmp/

# SSH to server and restore
ssh ec2-user@YOUR_DOMAIN
cd /opt/bloaty
gunzip /tmp/bloaty-2024-01-15.sql.gz
docker-compose exec -T db psql -U postgres bloaty < /tmp/bloaty-2024-01-15.sql
```

---

## Future: Terraform

This manual setup is designed to be converted to Terraform. Key resources to codify:

- `aws_instance` (EC2)
- `aws_eip` (Elastic IP)
- `aws_security_group`
- `aws_iam_role` + `aws_iam_role_policy`
- `aws_s3_bucket` + lifecycle rules
- `aws_secretsmanager_secret`
- `aws_route53_record`

The `deploy/` scripts can remain as-is for server configuration (Terraform handles infrastructure, scripts handle application setup).

---

## TODO

- [ ] **Fix SSL auto-renewal**: Current setup uses `--standalone` which fails because nginx holds port 80. Switch to webroot method:
  1. Add shared `/var/www/certbot` volume to `docker-compose.prod.yml` (nginx needs to serve `/.well-known/acme-challenge/`)
  2. Switch certbot preferred authenticator from `standalone` to `webroot` (`sudo certbot certonly --webroot -w /var/www/certbot -d bloaty-app.com --force-renewal`)
  3. Update cron job in `setup-ec2.sh` to use `certbot renew --webroot -w /var/www/certbot`
  - **Context**: Cert expired 2026-02-21, manually renewed with standalone (expires 2026-05-22)
