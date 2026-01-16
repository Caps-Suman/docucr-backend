#!/bin/bash

# Destroy Docu-CR Backend Infrastructure
# Usage: ./deploy/destroy.sh [region]

set -e

REGION=${1:-us-east-1}
PROJECT_NAME="docu-cr-backend"

echo "WARNING: This will destroy ALL infrastructure and data!"
echo "Region: $REGION"
echo "Project: $PROJECT_NAME"
echo ""
read -p "Are you sure you want to continue? (type 'yes' to confirm): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Destruction cancelled."
    exit 0
fi

echo "Starting infrastructure destruction..."

# Try Terraform destroy first
echo "1. Attempting Terraform destroy..."
cd deploy/terraform
if terraform destroy -auto-approve; then
    echo "Terraform destroy completed successfully"
    cd ../..
else
    echo "Terraform destroy failed, proceeding with manual cleanup..."
    cd ../..
    
    # Manual cleanup
    echo "2. Manual cleanup - Scaling down ECS service..."
    aws ecs update-service \
        --cluster ${PROJECT_NAME}-cluster \
        --service ${PROJECT_NAME}-service \
        --desired-count 0 \
        --region $REGION || echo "ECS service not found or already scaled down"
    
    echo "3. Waiting for tasks to stop..."
    sleep 30
    
    echo "4. Deleting ECS service..."
    aws ecs delete-service \
        --cluster ${PROJECT_NAME}-cluster \
        --service ${PROJECT_NAME}-service \
        --region $REGION || echo "ECS service not found"
    
    echo "5. Deleting ECS cluster..."
    aws ecs delete-cluster \
        --cluster ${PROJECT_NAME}-cluster \
        --region $REGION || echo "ECS cluster not found"
    
    echo "6. Deleting RDS instance..."
    aws rds delete-db-instance \
        --db-instance-identifier ${PROJECT_NAME}-db \
        --skip-final-snapshot \
        --region $REGION || echo "RDS instance not found"
    
    echo "7. Deleting ElastiCache..."
    aws elasticache delete-replication-group \
        --replication-group-id ${PROJECT_NAME}-redis \
        --region $REGION || echo "ElastiCache not found"
    
    echo "8. Deleting secrets..."
    aws secretsmanager delete-secret \
        --secret-id ${PROJECT_NAME}/rds \
        --force-delete-without-recovery \
        --region $REGION || echo "RDS secret not found"
    
    aws secretsmanager delete-secret \
        --secret-id ${PROJECT_NAME}/database-url \
        --force-delete-without-recovery \
        --region $REGION || echo "Database URL secret not found"
    
    aws secretsmanager delete-secret \
        --secret-id ${PROJECT_NAME}/app \
        --force-delete-without-recovery \
        --region $REGION || echo "App secret not found"
fi

echo "9. Deleting ECR repository..."
aws ecr delete-repository \
    --repository-name $PROJECT_NAME \
    --force \
    --region $REGION || echo "ECR repository not found"

echo ""
echo "Destruction completed!"
echo ""
echo "Note: Some resources (like VPC, subnets) may take a few minutes to fully delete."
echo "You can verify cleanup with:"
echo "  aws ecs list-clusters --region $REGION"
echo "  aws rds describe-db-instances --region $REGION"
echo "  aws secretsmanager list-secrets --region $REGION"