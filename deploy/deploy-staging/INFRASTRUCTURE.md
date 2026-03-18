# DocuCR Staging Infrastructure

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud (us-east-1)                    │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                      Default VPC                            │ │
│  │                                                              │ │
│  │  ┌──────────────────┐         ┌──────────────────┐         │ │
│  │  │   EC2 Instance   │────────▶│   RDS PostgreSQL │         │ │
│  │  │   (t3.small)     │         │   (db.t3.micro)  │         │ │
│  │  │                  │         │                  │         │ │
│  │  │  - Docker        │         │  - PostgreSQL    │         │ │
│  │  │  - Nginx         │         │    15.14         │         │ │
│  │  │  - App Container │         │  - 20GB Storage  │         │ │
│  │  │                  │         │  - Encrypted     │         │ │
│  │  └──────────────────┘         └──────────────────┘         │ │
│  │          │                                                   │ │
│  │          │ Pulls Images                                     │ │
│  │          ▼                                                   │ │
│  │  ┌──────────────────┐                                       │ │
│  │  │   ECR Registry   │                                       │ │
│  │  │                  │                                       │ │
│  │  │  - Docker Images │                                       │ │
│  │  │  - Auto Scan     │                                       │ │
│  │  └──────────────────┘                                       │ │
│  │                                                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
         │                                    │
         │ HTTP/HTTPS                         │ SSH
         ▼                                    ▼
    Internet Users                      Developers
```

## Services

### 1. **EC2 Instance** (Compute)
- **Type**: t3.small
- **OS**: Amazon Linux 2023
- **IP**: Use `terraform output ec2_public_ip`
- **Storage**: 30GB gp3 (encrypted)
- **Purpose**: Hosts Docker containers running the backend application

**Installed Software**:
- Docker & Docker Compose
- Nginx (reverse proxy)
- PostgreSQL client
- Git

**Security Group**:
- Port 22 (SSH) - Open to 0.0.0.0/0
- Port 80 (HTTP) - Open to 0.0.0.0/0
- Port 443 (HTTPS) - Open to 0.0.0.0/0
- Port 8000 (App) - Open to 0.0.0.0/0

**IAM Role**: `docucr-staging-ec2-ecr-role`
- Permissions: AmazonEC2ContainerRegistryReadOnly

### 2. **RDS PostgreSQL** (Database)
- **Engine**: PostgreSQL 15.14
- **Instance**: db.t3.micro
- **Storage**: 20GB gp3 (encrypted, auto-scaling up to 50GB)
- **Endpoint**: Use `terraform output rds_address`
- **Database**: docucr_staging
- **Schema**: docucr
- **Backup**: 1 day retention

**Security Group**:
- Port 5432 - From EC2 security group
- Port 5432 - Open to 0.0.0.0/0 (for development access)

**Connection**:
```bash
# Get connection details from terraform
terraform output -raw database_url
```

### 3. **ECR (Elastic Container Registry)**
- **Repository**: docucr-staging-backend
- **URL**: Use `terraform output ecr_repository_url`
- **Features**:
  - Image scanning on push
  - AES256 encryption
  - Lifecycle policy: Keep last 5 images

**Usage**:
```bash
# Get ECR URL
ECR_REPO=$(terraform output -raw ecr_repository_url)

# Login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_REPO

# Push
docker tag app:latest $ECR_REPO:latest
docker push $ECR_REPO:latest
```

### 4. **VPC & Networking**
- **VPC**: Default VPC
- **Subnets**: Default subnets across multiple AZs
- **Internet Gateway**: Default IGW
- **Public IP**: Auto-assigned to EC2

## Service Connections

### EC2 → RDS
- **Protocol**: PostgreSQL (TCP/5432)
- **Authentication**: Username/Password
- **Connection String**: Set via environment variable `DATABASE_URL`
- **Security**: EC2 security group whitelisted in RDS security group

### EC2 → ECR
- **Protocol**: HTTPS (TCP/443)
- **Authentication**: IAM Role (EC2 instance profile)
- **Purpose**: Pull Docker images for deployment
- **Security**: IAM role with ECR read-only permissions

### Internet → EC2
- **Protocol**: HTTP/HTTPS (TCP/80, 443, 8000)
- **Purpose**: Access backend API
- **Endpoints**:
  - Use `terraform output ec2_public_ip` for IP
  - Health check: `http://<EC2_IP>:8000/health`

### Developer → EC2
- **Protocol**: SSH (TCP/22)
- **Authentication**: SSH key pair (docu-cr-backend-key)
- **Command**: Use `terraform output ssh_command`

## Application Flow

1. **Build & Deploy**:
   ```
   Developer → Build Docker Image → Push to ECR → SSH to EC2 → Pull from ECR → Run Container
   ```

2. **Runtime**:
   ```
   User Request → EC2:8000 → Docker Container → RDS PostgreSQL → Response
   ```

3. **Data Flow**:
   ```
   Frontend (<EC2_IP>:8000) ← HTTP → Backend Container ← PostgreSQL → RDS Database
   ```

## Environment Variables

The application container receives:
- `DATABASE_URL`: Full PostgreSQL connection string
- `DB_SCHEMA`: docucr
- `ENVIRONMENT`: staging
- `PORT`: 8000

## Deployment Process

1. **Build**: `docker build -t docucr-backend:staging .`
2. **Push to ECR**: Tag and push to ECR repository
3. **Deploy**: SSH to EC2, pull image, restart container
4. **Automated**: Run `./deploy.sh` script

## Monitoring & Logs

- **Application Logs**: `docker-compose logs -f` on EC2
- **System Logs**: `/var/log/` on EC2
- **RDS Logs**: CloudWatch Logs (if enabled)

## Backup & Recovery

- **Database**: Automated daily backups (1 day retention)
- **Manual Backup**: `pg_dump` to local file
- **Restore**: Use `restore-db.sh` script

## Cost Estimate (Monthly)

- EC2 t3.small: ~$15
- RDS db.t3.micro: ~$15
- EBS Storage (30GB): ~$3
- RDS Storage (20GB): ~$2
- ECR Storage (~2GB): ~$0.20
- Data Transfer: ~$1-5
- **Total**: ~$36-40/month

## Security Features

✅ Encrypted EBS volumes
✅ Encrypted RDS storage
✅ IAM roles (no hardcoded credentials)
✅ Security groups with least privilege
✅ ECR image scanning
✅ SSH key-based authentication

## Access Information

- **API URL**: Use `terraform output ec2_public_ip`
- **SSH**: Use `terraform output ssh_command`
- **Database**: Use `terraform output database_url`
- **ECR**: Use `terraform output ecr_repository_url`

## Useful Commands

```bash
# Get all infrastructure details
cd terraform && terraform output

# Deploy application
./deploy.sh

# Restore database
./restore-db.sh

# SSH to EC2
EC2_IP=$(cd terraform && terraform output -raw ec2_public_ip)
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP

# Check application status
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP "cd /home/ec2-user/app && docker-compose ps"

# View logs
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP "cd /home/ec2-user/app && docker-compose logs -f"
```

## Troubleshooting

**Container not starting?**
```bash
EC2_IP=$(cd terraform && terraform output -raw ec2_public_ip)
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP
cd /home/ec2-user/app
docker-compose logs
```

**Database connection issues?**
```bash
# Test from EC2
DB_URL=$(cd terraform && terraform output -raw database_url)
psql "$DB_URL"
```

**Can't pull from ECR?**
```bash
# Check IAM role on EC2
aws sts get-caller-identity
```
