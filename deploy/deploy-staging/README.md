# Staging Environment - Terraform

## 💰 Estimated Cost: ~$49-53/month

### Cost Breakdown:
- EC2 t3.small: $15.18/month
- RDS db.t3.small: $24.82/month
- EBS Storage (30GB): $2.40/month
- RDS Storage (20GB): $2.30/month
- RDS Backups (5 days): ~$8.14/month
- ECR Storage (~2GB): $0.20/month
- Other: ~$1-2/month

**Capacity**: 50-60 concurrent users

---

## 📁 Project Structure

```
terraform-staging/
├── main.tf              # Provider configuration
├── vpc.tf               # VPC data sources
├── ec2.tf               # EC2 instance & Elastic IP
├── ecr.tf               # ECR repository
├── iam.tf               # IAM roles for EC2
├── rds.tf               # RDS database & security
├── variables.tf         # Input variables
├── outputs.tf           # Output values
├── terraform.tfvars     # Variable values (gitignored)
├── user-data.sh         # EC2 initialization script
├── deploy.sh            # Deployment script
├── restore-db.sh        # Database restore script
├── destroy.sh           # Destroy helper
└── README.md            # This file
```

---

## 🏗️ Architecture

```
Default VPC
  ├── EC2 t3.small (Elastic IP)
  │   - Docker + Docker Compose
  │   - Nginx + SSL (Certbot)
  │   - Backend App (Port 8000)
  │   - IAM Role (ECR access)
  │
  ├── RDS db.t3.small (Private)
  │   - PostgreSQL 15.14
  │   - 20GB gp3 storage
  │   - 5 days backup retention
  │
  └── ECR Repository
      - Image scanning enabled
      - Lifecycle: Keep last 5 images
```

**Domain**: Configured via terraform.tfvars
**Capacity**: 50-60 concurrent users

---

## 🚀 Quick Start

### Deploy Infrastructure & Application

```bash
cd deploy/terraform-staging

# 1. Initialize Terraform
terraform init

# 2. Deploy infrastructure
terraform apply

# 3. Deploy application
./deploy.sh
```

**That's it!** Application will be available at your configured domain

---

## 📦 Deployment

### Automated Deployment Script

```bash
cd deploy/terraform-staging
./deploy.sh
```

**What it does:**
1. Builds Docker image locally
2. Pushes to ECR
3. SSHs to EC2
4. Pulls latest image
5. Restarts application

### Manual Deployment

```bash
# 1. Build and push
ECR_REPO=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO
docker build -t docucr-backend:staging .
docker tag docucr-backend:staging $ECR_REPO:latest
docker push $ECR_REPO:latest

# 2. Deploy on EC2
EC2_IP=$(terraform output -raw ec2_public_ip)
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP
cd /home/ec2-user/app
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO
docker-compose pull
docker-compose up -d
```

### Database Restore

```bash
cd deploy/terraform-staging
./restore-db.sh
```

---

## 🔑 Access Information

```bash
# Get all details
terraform output

# Specific outputs
terraform output ec2_public_ip
terraform output -raw database_url
terraform output -raw ecr_repository_url
terraform output -raw ssh_command
```

---

## 📦 Post-Deployment Setup

### 1. SSH into EC2

```bash
# Get SSH command
terraform output -raw ssh_command

# Or manually
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@<EC2_IP>
```

### 2. Setup Application

```bash
cd ~/app

# Get database URL
DB_URL=$(terraform output -raw database_url)

# Create docker-compose.yml
cat > docker-compose.yml << EOF
version: '3.8'

services:
  backend:
    image: $(terraform output -raw ecr_repository_url):latest
    container_name: docucr-staging
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=$DB_URL
      - DB_SCHEMA=docucr
      - ENVIRONMENT=staging
      - PORT=8000
    restart: unless-stopped
EOF

# Login to ECR
ECR_REPO=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPO

# Start application
docker-compose up -d

# Check logs
docker-compose logs -f
```

### 3. Setup Nginx (Optional)

```bash
sudo cp /etc/nginx/conf.d/app.conf.template /etc/nginx/conf.d/app.conf
sudo systemctl restart nginx
```

### 4. Setup SSL (Optional)

```bash
# Point domain to EC2 IP first
sudo certbot --nginx -d staging.medeye360.com
```

---

## 🔧 Management

### View Application Logs
```bash
ssh ec2-user@<EC2_IP>
cd ~/app
docker-compose logs -f
```

### Restart Application
```bash
ssh ec2-user@<EC2_IP>
cd ~/app
docker-compose restart
```

### Update Application
```bash
ssh ec2-user@<EC2_IP>
cd ~/app
./deploy.sh  # Uses the pre-created deployment script
```

### Connect to Database
```bash
# From local machine
DB_URL=$(terraform output -raw database_url)
psql "$DB_URL"

# Or with details
psql -h <RDS_ENDPOINT> -U docucr_staging -d docucr_staging
```

---

## 🗑️ Destroy Infrastructure

### Option 1: Using Helper Script
```bash
./destroy.sh
```

### Option 2: Manual
```bash
terraform destroy
```

---

## 📊 Monitoring

### Application Status
```bash
# Check health (use domain from terraform.tfvars or IP)
EC2_IP=$(terraform output -raw ec2_public_ip)
curl http://$EC2_IP:8000/health

# View logs
ssh ec2-user@$EC2_IP "cd /home/ec2-user/app && docker-compose logs -f"

# Check container status
ssh ec2-user@$EC2_IP "docker ps"
```

### Infrastructure Status
```bash
# EC2 status
aws ec2 describe-instances --instance-ids $(terraform output -raw ec2_instance_id)

# RDS status  
aws rds describe-db-instances --db-instance-identifier docucr-staging-db

# SSL certificate expiry (if domain configured)
EC2_IP=$(terraform output -raw ec2_public_ip)
ssh ec2-user@$EC2_IP "sudo certbot certificates"
```

---

## 💡 Cost Optimization

### Save ~$15/month: Stop EC2 when not in use
```bash
INSTANCE_ID=$(terraform output -raw ec2_instance_id)
aws ec2 stop-instances --instance-ids $INSTANCE_ID --region us-east-1

# Start when needed
aws ec2 start-instances --instance-ids $INSTANCE_ID --region us-east-1
```

### Save ~$7/month: Use t3.micro instead
```hcl
# In terraform.tfvars
instance_type = "t3.micro"
```

### Save ~$1/month: Reduce storage
```hcl
# In terraform.tfvars
ec2_volume_size = 10
db_allocated_storage = 10
```

---

## 🔐 Security Best Practices

1. **Restrict SSH access**
   ```hcl
   # In ec2.tf, change SSH ingress
   cidr_blocks = ["YOUR_IP/32"]
   ```

2. **Disable RDS public access** (after setup)
   ```hcl
   # In terraform.tfvars
   db_publicly_accessible = false
   ```

3. **Enable MFA** for AWS account

4. **Rotate passwords** regularly
   ```bash
   terraform taint random_password.db_password
   terraform apply
   ```

---

## 🐛 Troubleshooting

### EC2 not accessible
```bash
# Check security group
aws ec2 describe-security-groups --group-ids <SG_ID>

# Check instance status
aws ec2 describe-instance-status --instance-ids <INSTANCE_ID>
```

### RDS connection failed
```bash
# Test connection
telnet <RDS_ENDPOINT> 5432

# Check security group
aws rds describe-db-instances --db-instance-identifier docucr-staging-db
```

### Docker not working
```bash
ssh ec2-user@<EC2_IP>
sudo systemctl status docker
sudo journalctl -u docker -f
```

---

## 📞 Support

For issues:
- Check `/var/log/user-data.log` on EC2
- Check `docker-compose logs`
- Check `/var/log/nginx/error.log`
- Review Terraform state: `terraform show`
