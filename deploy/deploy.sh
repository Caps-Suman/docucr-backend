#!/bin/bash
set -e

echo "=========================================="
echo "Deploying Docu-CR Backend"
echo "=========================================="
echo ""

# Get AWS Account ID and generate unique image tag
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
IMAGE_TAG=$(date +%Y%m%d-%H%M%S)
REGION="us-east-1"
REPO_NAME="docu-cr-backend"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}"

echo "Deployment Info:"
echo "   Account ID: ${AWS_ACCOUNT_ID}"
echo "   Image Tag: ${IMAGE_TAG}"
echo "   Region: ${REGION}"
echo "   ECR URI: ${ECR_URI}"
echo ""

cd "$(dirname "$0")"

# ECR Login
echo "Logging into ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Build
echo "Building Docker image..."
docker build -t ${REPO_NAME}:${IMAGE_TAG} ..

# Tag
echo "Tagging images..."
docker tag ${REPO_NAME}:${IMAGE_TAG} ${ECR_URI}:${IMAGE_TAG}
docker tag ${REPO_NAME}:${IMAGE_TAG} ${ECR_URI}:latest

# Push
echo "Pushing to ECR..."
docker push ${ECR_URI}:${IMAGE_TAG}
docker push ${ECR_URI}:latest

# Deploy
echo "Deploying to ECS..."
aws ecs update-service \
  --cluster docu-cr-backend-cluster \
  --service docu-cr-backend-service \
  --force-new-deployment \
  --region ${REGION} \
  --no-cli-pager

echo ""
echo "=========================================="
echo "DEPLOYMENT COMPLETE!"
echo "=========================================="
echo ""
echo "Image: ${ECR_URI}:${IMAGE_TAG}"
echo "Backend API: https://your-backend-domain.com"
echo "API Docs: https://your-backend-domain.com/docs"
echo "Health: https://your-backend-domain.com/health"
echo ""
echo "Monitor logs:"
echo "   aws logs tail /ecs/docu-cr-backend --follow --region ${REGION}"
echo ""
