# Backend Deployment

# if you are copying the infra and deploying different priject in the current infa then copy the state file first in current project 
cp /Users/apple/Documents/OCR/Docu-CR/backend/deploy/terraform/terraform.tfstate /Users/apple/Documents/OCR/docucr/docucr-backend/deploy/terraform/
terraform apply

# Force new deployment 
aws ecs update-service --cluster docu-cr-backend-cluster --service docu-cr-backend-service --force-new-deployment --region us-east-1


## Architecture Overview

### AWS Services Used

**Compute & Container:**
- **ECS Fargate**: Serverless container orchestration for running the FastAPI backend
  - Why: No server management, auto-scaling, pay-per-use
  - How: Runs Docker containers with the backend application

- **ECR (Elastic Container Registry)**: Docker image storage
  - Why: Secure, private Docker registry integrated with ECS
  - How: Stores versioned backend Docker images

**Database:**
- **RDS PostgreSQL**: Managed relational database
  - Why: Reliable, automated backups, multi-AZ support
  - How: Stores all application data (users, documents, metadata)
  - Schema: `docucr`

**Networking:**
- **Application Load Balancer (ALB)**: HTTPS traffic distribution
  - Why: SSL termination, health checks, high availability
  - How: Routes traffic to ECS tasks on port 8000

- **VPC**: Isolated network environment
  - Why: Security, network isolation
  - How: Private subnets for backend, public subnets for ALB

**Security:**
- **Secrets Manager**: Secure credential storage
  - Why: Encrypted storage, automatic rotation
  - How: Stores database credentials, JWT secrets, admin passwords
  - Secrets: `docu-cr-backend/rds`, `docu-cr-backend/database-url`, `docu-cr-backend/app`

- **IAM Roles**: Service permissions
  - Why: Least privilege access control
  - How: ECS task role for accessing RDS, Secrets Manager, S3

**Monitoring:**
- **CloudWatch Logs**: Centralized logging
  - Why: Debugging, monitoring, alerting
  - How: Streams logs from ECS containers to `/ecs/docu-cr-backend`

### How Services Work Together

```
User Request (HTTPS)
    ↓
Application Load Balancer (Port 443)
    ↓
ECS Fargate (FastAPI Container)
    ↓
├─→ RDS PostgreSQL (Data Storage)
└─→ Secrets Manager (Credentials)
```

**Request Flow:**
1. User sends HTTPS request to custom domain
2. ALB terminates SSL and forwards to ECS task
3. FastAPI app authenticates using JWT from Secrets Manager
4. App queries PostgreSQL for data
5. Response sent back through ALB to user

## Quick Deploy

```bash
cd backend
./deploy.sh
```

This will:
1. Build Docker image
2. Push to ECR
3. Deploy to ECS

## Scripts

### `deploy.sh` - Main Deployment Script
Builds, pushes, and deploys the backend.

```bash
./deploy.sh
```

### `destroy.sh` - Destroy Infrastructure
Destroys all backend infrastructure.

```bash
./deploy/destroy.sh [region]
```

## Initial Setup

### Step 1: Deploy Infrastructure with Terraform
```bash
cd deploy/terraform

# Initialize Terraform
terraform init

# Review changes
terraform plan

# Deploy infrastructure
terraform apply
```

### Step 2: Deploy Application
```bash
cd ../..
./deploy.sh
```

The database will be automatically initialized on first deployment.

## Update Deployment

For code changes, simply run:
```bash
./deploy.sh
```

## Monitoring

### View Logs
```bash
aws logs tail /ecs/docu-cr-backend --follow
```

### Check Service Status
```bash
aws ecs describe-services --cluster docu-cr-backend-cluster --services docu-cr-backend-service
```

### Health Check
```bash
curl https://your-backend-domain.com/health
```

## Cost Breakdown

Estimated monthly costs:
- **ECS Fargate**: ~$30 (0.25 vCPU, 0.5 GB RAM)
- **RDS PostgreSQL**: ~$15 (db.t3.micro)
- **Application Load Balancer**: ~$20
- **NAT Gateway**: ~$32
- **ECR Storage**: ~$1
- **CloudWatch Logs**: ~$3
- **Total**: ~$101/month

## Cleanup

**Warning**: This will delete all infrastructure and data permanently.

```bash
./deploy/destroy.sh
```

Or manually with Terraform:
```bash
cd deploy/terraform
terraform destroy
```

## Troubleshooting

### ECS Task Not Starting
```bash
# Check task logs
aws ecs describe-tasks --cluster docu-cr-backend-cluster --tasks <task-id>

# Check CloudWatch logs
aws logs tail /ecs/docu-cr-backend --since 10m
```

### Database Connection Issues
```bash
# Verify RDS is running
aws rds describe-db-instances --db-instance-identifier docu-cr-backend-db

# Check security group rules
aws ec2 describe-security-groups --group-ids <sg-id>
```

### Secrets Not Found
```bash
# List all secrets
aws secretsmanager list-secrets --query 'SecretList[?contains(Name, `docu-cr-backend`)].Name'
```
