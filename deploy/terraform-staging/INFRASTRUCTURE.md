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
- **IP**: 3.238.106.39
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
- **Endpoint**: docucr-staging-db.cg7xyuwv2b96.us-east-1.rds.amazonaws.com:5432
- **Database**: docucr_staging
- **Schema**: docucr
- **Backup**: 1 day retention

**Security Group**:
- Port 5432 - From EC2 security group
- Port 5432 - Open to 0.0.0.0/0 (for development access)

**Connection**:
```bash
psql -h docucr-staging-db.cg7xyuwv2b96.us-east-1.rds.amazonaws.com \
     -U docucr_staging \
     -d docucr_staging
```

### 3. **ECR (Elastic Container Registry)**
- **Repository**: docucr-staging-backend
- **URL**: 288373392300.dkr.ecr.us-east-1.amazonaws.com/docucr-staging-backend
- **Features**:
  - Image scanning on push
  - AES256 encryption
  - Lifecycle policy: Keep last 5 images

**Usage**:
```bash
# Login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  288373392300.dkr.ecr.us-east-1.amazonaws.com

# Push
docker tag app:latest 288373392300.dkr.ecr.us-east-1.amazonaws.com/docucr-staging-backend:latest
docker push 288373392300.dkr.ecr.us-east-1.amazonaws.com/docucr-staging-backend:latest
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
  - `http://3.238.106.39:8000` - Direct API access
  - `http://3.238.106.39:8000/health` - Health check

### Developer → EC2
- **Protocol**: SSH (TCP/22)
- **Authentication**: SSH key pair (docu-cr-backend-key)
- **Command**: `ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@3.238.106.39`

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
   Frontend (3.238.106.39:8000) ← HTTP → Backend Container ← PostgreSQL → RDS Database
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

- **API URL**: http://3.238.106.39:8000
- **SSH**: `ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@3.238.106.39`
- **Database**: See Terraform outputs for credentials
- **ECR**: 288373392300.dkr.ecr.us-east-1.amazonaws.com/docucr-staging-backend

## Useful Commands

```bash
# Get all infrastructure details
terraform output

# Deploy application
./deploy.sh

# Restore database
./restore-db.sh

# SSH to EC2
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@3.238.106.39

# Check application status
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@3.238.106.39 "cd /home/ec2-user/app && docker-compose ps"

# View logs
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@3.238.106.39 "cd /home/ec2-user/app && docker-compose logs -f"
```

## Troubleshooting

**Container not starting?**
```bash
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@3.238.106.39
cd /home/ec2-user/app
docker-compose logs
```

**Database connection issues?**
```bash
# Test from EC2
psql -h docucr-staging-db.cg7xyuwv2b96.us-east-1.rds.amazonaws.com -U docucr_staging -d docucr_staging
```

**Can't pull from ECR?**
```bash
# Check IAM role on EC2
aws sts get-caller-identity
```
