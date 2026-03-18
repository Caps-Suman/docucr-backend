# Staging Deployment Guide

## Prerequisites
- Docker installed locally
- AWS CLI configured
- SSH key: `~/.ssh/docu-cr-backend-key.pem`
- Secrets stored in AWS Secrets Manager: `docucr-staging/app`

## Automated Deployment

### Deploy Code Changes
```bash
cd deploy/deploy-staging
./deploy.sh
```

This script automatically:
- Builds and pushes Docker image to ECR
- Fetches secrets from AWS Secrets Manager
- Deploys to EC2 with docker-compose

### Configure Nginx (One-time setup)
```bash
cd deploy/deploy-staging
./configure-nginx.sh
```

Run this only when:
- Setting up a new EC2 instance
- Updating Nginx configuration
- Fixing WebSocket connection issues

### Other Management Scripts
```bash
# Check infrastructure status
./check-status.sh

# Destroy infrastructure
./destroy.sh

# Restore database from backup
./restore-db.sh
```

## Manual Deployment Steps

### Step 1: Get Infrastructure Details
```bash
cd deploy/deploy-staging/terraform
terraform output
```

### Step 2: Build and Push Docker Image
```bash
cd deploy/deploy-staging

# Get ECR repository URL
ECR_REPO=$(cd terraform && terraform output -raw ecr_repository_url)

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO

# Build and push
cd ../../
docker build -t docucr-backend:staging .
docker tag docucr-backend:staging $ECR_REPO:latest
docker push $ECR_REPO:latest
```

### Step 3: Deploy to EC2
```bash
# Get EC2 IP
EC2_IP=$(cd terraform && terraform output -raw ec2_public_ip)

# SSH to EC2
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP

# On EC2: Pull and deploy
cd /home/ec2-user/app
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ECR_REPO>
docker-compose pull
docker-compose up -d
```

## Access Application

- **API**: https://docucrapi.medeye360.com
- **Health Check**: https://docucrapi.medeye360.com/health
- **SSH**: `ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$(cd terraform && terraform output -raw ec2_public_ip)`

## Troubleshooting

### View Logs
```bash
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@<EC2_IP>
cd /home/ec2-user/app
docker-compose logs -f
```

### Check Nginx Status
```bash
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@<EC2_IP>
sudo systemctl status nginx
sudo nginx -t
```

### WebSocket Issues
If WebSocket connections fail, run:
```bash
cd deploy/deploy-staging
./configure-nginx.sh
```
