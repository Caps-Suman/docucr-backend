# Staging Deployment Guide

## Prerequisites
- Docker installed locally
- AWS CLI configured
- SSH key: `~/.ssh/docu-cr-backend-key.pem`

## Step 1: Get Infrastructure Details
```bash
cd deploy/terraform-staging
terraform output
```

## Step 2: Build and Push Docker Image to ECR

```bash
# Get ECR repository URL
ECR_REPO=$(cd terraform && terraform output -raw ecr_repository_url)
AWS_REGION="us-east-1"

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO

# Build image (from backend root)
cd ../..
docker build -t docucr-backend:staging .

# Tag and push to ECR
docker tag docucr-backend:staging $ECR_REPO:latest
docker push $ECR_REPO:latest
```

## Step 3: SSH to EC2 and Deploy

```bash
# Get EC2 IP
EC2_IP=$(cd terraform && terraform output -raw ec2_public_ip)

# SSH to EC2
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP

# On EC2 instance:
cd /home/ec2-user/app

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  backend:
    image: YOUR_ECR_REPO_URL:latest
    container_name: docucr-staging
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=YOUR_DATABASE_URL
      - DB_SCHEMA=docucr
      - ENVIRONMENT=staging
      - PORT=8000
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
EOF

# Login to ECR from EC2
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ECR_REPO

# Pull and run
docker-compose pull
docker-compose up -d

# Check logs
docker-compose logs -f
```

## Step 4: Configure Nginx (Optional)

```bash
# On EC2, copy template and restart nginx
sudo cp /etc/nginx/conf.d/app.conf.template /etc/nginx/conf.d/app.conf
sudo systemctl restart nginx
```

## Quick Deploy Script

Save this as `deploy/terraform-staging/quick-deploy.sh`:

```bash
#!/bin/bash
set -e

cd "$(dirname "$0")"

# Get outputs
cd terraform
ECR_REPO=$(terraform output -raw ecr_repository_url)
EC2_IP=$(terraform output -raw ec2_public_ip)
DB_URL=$(terraform output -raw database_url)
cd ..

echo "Building and pushing to ECR..."
cd ../..
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO
docker build -t docucr-backend:staging .
docker tag docucr-backend:staging $ECR_REPO:latest
docker push $ECR_REPO:latest

echo "Deploying to EC2..."
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP << EOF
  cd /home/ec2-user/app
  
  # Create docker-compose.yml
  cat > docker-compose.yml << 'COMPOSE'
version: '3.8'
services:
  backend:
    image: $ECR_REPO:latest
    container_name: docucr-staging
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=$DB_URL
      - DB_SCHEMA=docucr
      - ENVIRONMENT=staging
      - PORT=8000
    restart: unless-stopped
COMPOSE

  # Deploy
  aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO
  docker-compose pull
  docker-compose down || true
  docker-compose up -d
  
  echo "Deployment complete!"
  docker-compose ps
EOF

echo "✅ Deployed to http://$EC2_IP:8000"
```

Make it executable:
```bash
chmod +x deploy/terraform-staging/quick-deploy.sh
```

## Access Application

- **API**: Use `terraform output ec2_public_ip` for IP
- **Health Check**: `http://<EC2_IP>:8000/health`
- **SSH**: Use `terraform output ssh_command`
