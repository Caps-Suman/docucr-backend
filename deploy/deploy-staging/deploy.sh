#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Deploying Backend Code to Staging${NC}"
echo ""

# Get outputs from Terraform
echo -e "${GREEN}📍 Getting infrastructure details...${NC}"
cd terraform
ECR_REPO=$(terraform output -raw ecr_repository_url 2>/dev/null || echo "")
EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null || echo "")
DB_URL=$(terraform output -raw database_url 2>/dev/null || echo "")
cd ..

if [ -z "$EC2_IP" ] || [ -z "$ECR_REPO" ]; then
    echo -e "${RED}❌ Could not retrieve infrastructure details. Ensure Terraform is deployed.${NC}"
    exit 1
fi

echo -e "${YELLOW}Target EC2: $EC2_IP${NC}"
echo -e "${YELLOW}ECR Repo: $ECR_REPO${NC}"
echo ""

# Login to ECR
echo -e "${GREEN}🔐 Logging into ECR...${NC}"
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO

# Build Docker image
echo -e "${GREEN}🐳 Building Docker image...${NC}"
cd ../../
docker build -t docucr-backend:staging .

# Tag and push to ECR
echo -e "${GREEN}📦 Pushing to ECR...${NC}"
docker tag docucr-backend:staging $ECR_REPO:latest
docker push $ECR_REPO:latest

cd deploy/deploy-staging/

# Fetch secrets from Secrets Manager
echo -e "${GREEN}🔐 Fetching secrets from AWS Secrets Manager...${NC}"
SECRETS=$(aws secretsmanager get-secret-value --secret-id docucr-staging/app --region us-east-1 --query SecretString --output text)

# Parse secrets into environment variables
JWT_SECRET=$(echo $SECRETS | jq -r '.JWT_SECRET_KEY')
AWS_ACCESS_KEY_ID_SECRET=$(echo $SECRETS | jq -r '.AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY_SECRET=$(echo $SECRETS | jq -r '.AWS_SECRET_ACCESS_KEY')
AWS_S3_BUCKET=$(echo $SECRETS | jq -r '.AWS_S3_BUCKET')
SMTP_USER=$(echo $SECRETS | jq -r '.SMTP_USERNAME')
SMTP_PASSWORD=$(echo $SECRETS | jq -r '.SMTP_PASSWORD')
SMTP_FROM=$(echo $SECRETS | jq -r '.SENDER_EMAIL')
OPENAI_API_KEY=$(echo $SECRETS | jq -r '.OPENAI_API_KEY')

# Deploy to EC2
echo -e "${GREEN}🚀 Deploying to EC2...${NC}"
ssh -o StrictHostKeyChecking=no -i ~/Documents/fhrm/fhrm-pem-key/ivr-staging-key.pem ec2-user@$EC2_IP << ENDSSH
  set -e
  
  # Create app directory if not exists
  mkdir -p /home/ec2-user/app
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
      - JWT_SECRET_KEY=$JWT_SECRET
      - AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID_SECRET
      - AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY_SECRET
      - AWS_S3_BUCKET=$AWS_S3_BUCKET
      - SMTP_USERNAME=$SMTP_USER
      - SMTP_PASSWORD=$SMTP_PASSWORD
      - SENDER_EMAIL=$SMTP_FROM
      - OPENAI_API_KEY=$OPENAI_API_KEY
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
COMPOSE
  
  # Login to ECR from EC2
  aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO
  
  # Pull and deploy
  docker-compose pull
  docker-compose down || true
  docker-compose up -d
  
  echo "Deployment complete!"
  docker-compose ps
ENDSSH

echo ""
echo -e "${GREEN}✅ Backend deployment complete!${NC}"
echo -e "${YELLOW}Application running at: https://docucrapi.medeye360.com${NC}"
echo -e "${YELLOW}Health check: https://docucrapi.medeye360.com/health${NC}"
