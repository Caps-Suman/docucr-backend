# Terraform Infrastructure

This directory contains Terraform configuration for deploying the backend infrastructure on AWS.

## What Terraform Creates

### Core Infrastructure
- **VPC**: Isolated network (10.0.0.0/16)
- **Subnets**: 2 public subnets (for ALB) + 1 private subnet (for ECS/RDS)
- **Internet Gateway**: Public internet access
- **NAT Instance**: Cost-effective outbound internet for private resources (t3.nano, ~$6/month)
- **Route Tables**: Public and private routing
- **SSH Key Pair**: For bastion and NAT instance access

### Compute
- **ECS Cluster**: Container orchestration
- **ECS Service**: Runs FastAPI containers
- **ECS Task Definition**: Container configuration (0.25 vCPU, 0.5 GB RAM)

### Database
- **RDS PostgreSQL**: db.t3.micro instance
- **DB Subnet Group**: Multi-AZ database placement
- **Security Group**: Database access control

### Load Balancing
- **Application Load Balancer**: HTTPS traffic distribution
- **Target Group**: Routes traffic to ECS tasks
- **Listener**: HTTP/HTTPS endpoints

### Security
- **Security Groups**: Network access control for ALB, ECS, RDS
- **IAM Roles**: ECS task execution and task roles
- **Secrets Manager**: Database credentials, JWT secrets, admin password

### Bastion & Access
- **Bastion Host**: Secure access to private resources (t3.nano)
- **NAT Instance**: Handles outbound traffic for private subnet
- **SSH Access**: Key-based authentication using existing SSH keys

### Monitoring
- **CloudWatch Log Group**: `/ecs/docu-cr-backend`

## File Structure

```
terraform/
├── main.tf           # VPC, subnets, networking, ALB
├── ecs.tf            # ECS cluster, service, task definition
├── rds.tf            # PostgreSQL database
├── iam.tf            # IAM roles and policies
├── secrets.tf        # AWS Secrets Manager
├── bastion.tf        # Bastion host for secure access
├── keypair.tf        # SSH key pair (uses ~/Documents/fhrm-pem-key/ssh-key.pub)
├── nat_instance.tf   # NAT instance (replaces NAT Gateway)
├── variables.tf      # Input variables
├── outputs.tf        # Output values
├── terraform.tfvars.example  # Example configuration
└── terraform.tfvars  # Your actual configuration (gitignored)
```

## Initial Setup

### 1. Configure Variables

Copy the example file:
```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:
```hcl
aws_region      = "us-east-1"
project_name    = "docu-cr-backend"
environment     = "prod"
container_image = "YOUR_AWS_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/docu-cr-backend:latest"
db_username     = "aiicr_user"
db_name         = "aiicr"
db_schema       = "aiicr"
```

### 2. Initialize Terraform

```bash
cd deploy/terraform
terraform init
```

This downloads required providers (AWS, Random).

### 3. Review Changes

```bash
terraform plan
```

Review what will be created before applying.

### 4. Deploy Infrastructure

```bash
terraform apply
```

Type `yes` to confirm. This takes ~10-15 minutes.

### 5. Get Outputs

```bash
terraform output
```

Important outputs:
- `alb_dns_name`: Load balancer endpoint
- `ecs_cluster_name`: ECS cluster name
- `rds_endpoint`: Database endpoint
- `bastion_public_ip`: Bastion host IP address
- `bastion_ssh_command`: SSH command to connect to bastion
- `rds_tunnel_command`: SSH tunnel command for RDS access

## Deploying for a New Client

### Option 1: Separate AWS Account (Recommended)

**Best for**: Complete isolation, separate billing

1. **Create new AWS account** for the client
2. **Configure AWS CLI** with new account credentials:
   ```bash
   aws configure --profile client-name
   export AWS_PROFILE=client-name
   ```
3. **Copy terraform directory**:
   ```bash
   cp -r deploy/terraform deploy/terraform-client-name
   cd deploy/terraform-client-name
   ```
4. **Update terraform.tfvars**:
   ```hcl
   project_name = "client-name-backend"
   environment  = "prod"
   db_name      = "client_db"
   db_schema    = "client_schema"
   ```
5. **Deploy**:
   ```bash
   terraform init
   terraform apply
   ```

### Option 2: Same AWS Account, Different Project Name

**Best for**: Multiple environments, cost sharing

1. **Copy terraform directory**:
   ```bash
   cp -r deploy/terraform deploy/terraform-client-name
   cd deploy/terraform-client-name
   ```
2. **Update terraform.tfvars**:
   ```hcl
   project_name = "client-name-backend"  # CRITICAL: Must be unique
   environment  = "prod"
   db_name      = "client_db"
   db_schema    = "client_schema"
   ```
3. **Deploy**:
   ```bash
   terraform init
   terraform apply
   ```

### Option 3: Terraform Workspaces

**Best for**: Same codebase, multiple deployments

```bash
# Create workspace for new client
terraform workspace new client-name

# Switch to workspace
terraform workspace select client-name

# Update terraform.tfvars for this client
# Deploy
terraform apply
```

## Key Variables to Change Per Client

### Required Changes
```hcl
project_name = "client-name-backend"  # MUST be unique per client
db_name      = "client_db"            # Database name
db_schema    = "client_schema"        # Schema name
```

### Optional Changes
```hcl
aws_region   = "us-west-2"            # Different region
environment  = "staging"              # Environment name
db_username  = "client_user"          # Database username
```

### What Stays the Same
- VPC CIDR blocks (unless conflicts exist)
- Instance sizes (db.t3.micro, 0.25 vCPU)
- Port numbers (8000, 5432)
- Security group rules

## Important Notes

### Resource Naming
All resources are prefixed with `${project_name}`:
- ECS Cluster: `{project_name}-cluster`
- RDS Instance: `{project_name}-db`
- ALB: `{project_name}-alb`
- Secrets: `{project_name}/rds`, `{project_name}/app`

**CRITICAL**: `project_name` must be unique per deployment to avoid conflicts.

### Secrets Management
Terraform creates these secrets with random passwords:
- `{project_name}/rds`: Database credentials
- `{project_name}/database-url`: Full connection string
- `{project_name}/app`: JWT secret, admin credentials

**After deployment**, update admin credentials:
```bash
aws secretsmanager update-secret \
  --secret-id client-name-backend/app \
  --secret-string '{"ADMIN_EMAIL":"admin@client.com","ADMIN_PASSWORD":"SecurePass123!"}'
```

### Database Schema
The `db_schema` variable sets the PostgreSQL schema name. Each client should have a unique schema:
- Client A: `client_a_schema`
- Client B: `client_b_schema`

### Container Image
Each client deployment needs its own ECR repository or uses the same image with different configurations.

## Common Commands

### View Current State
```bash
terraform show
```

### List Resources
```bash
terraform state list
```

### Get Specific Output
```bash
terraform output alb_dns_name
```

### Update Infrastructure
```bash
# After changing variables or code
terraform plan
terraform apply
```

### Destroy Infrastructure
```bash
terraform destroy
```

**Warning**: This deletes everything including the database!

## Updating Existing Deployment

### Change Container Image
1. Update `container_image` in `terraform.tfvars`
2. Run:
   ```bash
   terraform apply
   ```

### Scale ECS Service
Edit `ecs.tf`:
```hcl
resource "aws_ecs_service" "app" {
  desired_count = 2  # Change from 1 to 2
  ...
}
```

Then apply:
```bash
terraform apply
```

### Change Database Size
Edit `rds.tf`:
```hcl
resource "aws_db_instance" "main" {
  instance_class = "db.t3.small"  # Upgrade from db.t3.micro
  ...
}
```

Then apply:
```bash
terraform apply
```

## Multi-Client Deployment Example

### Client 1: Acme Corp
```bash
cd deploy/terraform-acme
# terraform.tfvars
project_name = "acme-backend"
db_name      = "acme_db"
db_schema    = "acme"

terraform apply
```

### Client 2: TechStart Inc
```bash
cd deploy/terraform-techstart
# terraform.tfvars
project_name = "techstart-backend"
db_name      = "techstart_db"
db_schema    = "techstart"

terraform apply
```

### Result
- Separate VPCs, databases, ECS clusters
- Isolated resources per client
- Independent scaling and updates
- Separate billing (if different AWS accounts)

## Troubleshooting

### Error: Resource Already Exists
**Cause**: `project_name` conflicts with existing deployment

**Fix**: Change `project_name` to a unique value

### Error: Invalid CIDR Block
**Cause**: VPC CIDR conflicts with existing VPC

**Fix**: Edit `main.tf` and change VPC CIDR:
```hcl
resource "aws_vpc" "main" {
  cidr_block = "10.1.0.0/16"  # Change from 10.0.0.0/16
  ...
}
```

### Error: Container Image Not Found
**Cause**: ECR image doesn't exist yet

**Fix**: Build and push image first:
```bash
cd ../..
./deploy.sh
```

### State Lock Error
**Cause**: Another terraform process is running

**Fix**: Wait or force unlock:
```bash
terraform force-unlock <lock-id>
```

## Cost Optimization

### NAT Instance vs NAT Gateway
**Current Setup**: NAT Instance (t3.nano)
- **Cost**: ~$6/month
- **Savings**: $29/month vs NAT Gateway
- **Performance**: Up to 5 Gbps (sufficient for most workloads)
- **Trade-off**: Single-AZ (not HA like NAT Gateway)

**To switch back to NAT Gateway** (if needed for HA):
```bash
rm keypair.tf nat_instance.tf
git checkout main.tf bastion.tf
terraform apply
```

### Development Environment
```hcl
# Use smaller instances
instance_class = "db.t3.micro"
cpu           = "256"   # 0.25 vCPU
memory        = "512"   # 0.5 GB

# Single AZ
multi_az = false
```

### Production Environment
```hcl
# Larger instances
instance_class = "db.t3.small"
cpu           = "512"   # 0.5 vCPU
memory        = "1024"  # 1 GB

# Multi-AZ for high availability
multi_az = true
```

## Security Best Practices

1. **Never commit `terraform.tfvars`** - Contains sensitive data
2. **Use separate AWS accounts** for different clients
3. **Enable MFA** on AWS accounts
4. **Rotate secrets regularly** via Secrets Manager
5. **Review security groups** - Minimize open ports
6. **Enable CloudTrail** for audit logging
7. **Use private subnets** for ECS and RDS (already configured)

## Backup and Recovery

### Database Backups
RDS automatically creates daily backups (7-day retention).

**Manual backup**:
```bash
aws rds create-db-snapshot \
  --db-instance-identifier client-name-backend-db \
  --db-snapshot-identifier client-name-backup-$(date +%Y%m%d)
```

### Terraform State Backup
```bash
# Backup state file
cp terraform.tfstate terraform.tfstate.backup-$(date +%Y%m%d)

# Or use S3 backend (recommended for production)
```

## SSH Access to Infrastructure

### Prerequisites
SSH key pair must exist at: `~/Documents/fhrm-pem-key/ssh-key` (private) and `ssh-key.pub` (public)

### Connect to Bastion Host
```bash
# Get SSH command from Terraform output
terraform output bastion_ssh_command

# Or manually
ssh -i ~/Documents/fhrm-pem-key/ssh-key ec2-user@<BASTION_IP>
```

### Create RDS Tunnel
```bash
# Get tunnel command from Terraform output
terraform output rds_tunnel_command

# Or manually
ssh -i ~/Documents/fhrm-pem-key/ssh-key -L 5344:<RDS_ENDPOINT>:5432 ec2-user@<BASTION_IP> -N

# Then connect to localhost:5344 with your database client
psql -h localhost -p 5344 -U aiicr_user -d aiicr
```

### Access NAT Instance (for troubleshooting)
```bash
ssh -i ~/Documents/fhrm-pem-key/ssh-key ec2-user@<NAT_INSTANCE_IP>

# Check NAT status
sudo iptables -t nat -L -n -v
cat /proc/sys/net/ipv4/ip_forward  # Should show: 1
```

### Alternative: SSM Session Manager (no SSH key needed)
```bash
# Connect to bastion
aws ssm start-session --target <BASTION_INSTANCE_ID> --region us-east-1
```

## Next Steps

After Terraform deployment:
1. **Verify SSH access**: Test bastion connection
2. **Deploy application**: Run `../../deploy.sh`
3. **Configure DNS**: Point domain to ALB DNS name
4. **Add SSL certificate**: Update ALB listener for HTTPS
5. **Update secrets**: Set admin credentials
6. **Test deployment**: `curl https://your-domain.com/health`
7. **Set up monitoring**: Create CloudWatch alarms for NAT instance
