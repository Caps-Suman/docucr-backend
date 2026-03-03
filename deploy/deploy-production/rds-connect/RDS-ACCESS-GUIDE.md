# RDS Database Access Guide

## Architecture Overview

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Your PC   │ ──SSM──▶│ Bastion Host │ ──────▶│  RDS (DB)   │
│  (DBeaver)  │  Tunnel │  (EC2 t3.nano)│  5432  │ (Private)   │
└─────────────┘         └──────────────┘         └─────────────┘
   localhost:5344        Public Subnet           Private Subnet
```

### Why Bastion Host?

- **Security**: RDS is in a private subnet (no public access)
- **No SSH Keys**: Uses AWS Systems Manager (SSM) - IAM-based authentication
- **Audit Trail**: All connections logged in CloudTrail
- **Cost**: ~$3.50/month for t3.nano instance

## Prerequisites

1. **AWS CLI** configured with proper credentials
2. **AWS Session Manager Plugin** installed
3. **Database client** (DBeaver, pgAdmin, etc.)

## Setup Instructions

### 1. Install AWS Session Manager Plugin

**macOS:**
```bash
# Download
curl 'https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac/sessionmanager-bundle.zip' -o 'sessionmanager-bundle.zip'

# Unzip
unzip sessionmanager-bundle.zip

# Install (requires sudo password)
sudo ./sessionmanager-bundle/install -i /usr/local/sessionmanagerplugin -b /usr/local/bin/session-manager-plugin

# Verify
session-manager-plugin

# Clean up
rm -rf sessionmanager-bundle sessionmanager-bundle.zip
```

**Linux:**
```bash
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o "session-manager-plugin.deb"
sudo dpkg -i session-manager-plugin.deb
```

**Windows:**
Download from: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html

### 2. Deploy Bastion Host (One-Time)

```bash
cd backend/deploy/terraform
terraform apply
```

This creates:
- EC2 t3.nano instance in public subnet
- Security group allowing bastion → RDS access
- IAM role with SSM permissions
- No SSH keys required

## Connecting to RDS

### Quick Start

```bash
cd backend/deploy/rds-connect

# Get credentials
./get-rds-credentials.sh

# Start tunnel (keep terminal open)
./connect-rds.sh
```

### Step 1: Get Database Credentials

```bash
cd backend/deploy/rds-connect
./get-rds-credentials.sh
```

This displays:
- Host: `localhost`
- Port: `5344`
- Database: `aiicr`
- Username: `aiicr_user`
- Password: `[from Terraform output]`

### Step 2: Start the Tunnel

```bash
cd backend/deploy/rds-connect
./connect-rds.sh
```

**Keep this terminal open!** The tunnel runs until you press `Ctrl+C`.

You should see:
```
🔐 Connecting to RDS via AWS Systems Manager...
📍 RDS Host: docu-cr-backend-db.cg7xyuwv2b96.us-east-1.rds.amazonaws.com
🖥️  Bastion: i-064cf7dad0ccaab01

✅ Creating port forwarding tunnel...
   Local: localhost:5344 → Remote: docu-cr-backend-db...

📝 DBeaver Connection Settings:
   Host: localhost
   Port: 5344
   Database: aiicr
   Username: aiicr_user
   Password: (retrieve with './get-rds-credentials.sh')

Press Ctrl+C to close the tunnel
```

### Step 3: Connect with DBeaver

1. Open DBeaver
2. Click **Database** → **New Database Connection**
3. Select **PostgreSQL**
4. Enter connection details:
   - **Host:** `localhost`
   - **Port:** `5344`
   - **Database:** `aiicr`
   - **Username:** `aiicr_user`
   - **Password:** [from get-rds-credentials.sh]
5. Click **Test Connection**
6. Click **Finish**

### Step 4: Query the Database

```sql
-- List all tables
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'aiicr';

-- Query data
SELECT * FROM aiicr.users LIMIT 10;
```

### Step 5: Close the Tunnel

When done, press `Ctrl+C` in the terminal running the tunnel.

## Troubleshooting

### "SessionManagerPlugin is not found"
Install the Session Manager plugin (see Setup Instructions above).

### "Connection refused" or "Port not open"
- Ensure the tunnel is running (`./connect-rds.sh`)
- Check that no other service is using port 5344: `lsof -i :5344`

### "Password authentication failed"
Get the current password:
```bash
cd backend/deploy/rds-connect
./get-rds-credentials.sh
```

Or directly from Terraform:
```bash
cd backend/deploy/terraform
terraform output -raw db_password
```

### "Target not connected"
Wait 2-3 minutes after deployment for SSM agent to register.

Check status:
```bash
cd backend/deploy/terraform
BASTION_ID=$(terraform output -raw bastion_instance_id)
aws ec2 describe-instances --instance-ids $BASTION_ID --region us-east-1
```

## Manual Connection (Advanced)

```bash
cd backend/deploy/terraform

BASTION_ID=$(terraform output -raw bastion_instance_id)
RDS_HOST=$(terraform output -raw rds_endpoint | cut -d: -f1)

aws ssm start-session \
  --target $BASTION_ID \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$RDS_HOST\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5344\"]}" \
  --region us-east-1
```

## Cost Breakdown

| Resource | Type | Monthly Cost |
|----------|------|--------------|
| Bastion EC2 | t3.nano | ~$3.50 |
| Data Transfer | Minimal | ~$0.10 |
| **Total** | | **~$3.60/month** |

## Security Features

✅ **No SSH Keys** - Uses AWS IAM for authentication  
✅ **No Public RDS** - Database stays in private subnet  
✅ **Audit Logging** - All sessions logged in CloudTrail  
✅ **Encrypted Transit** - SSM uses TLS encryption  
✅ **IAM Policies** - Fine-grained access control  

## Useful Commands

```bash
# Check if tunnel is working
nc -zv localhost 5344

# Get all connection info
cd backend/deploy/terraform
terraform output

# List active SSM sessions
aws ssm describe-sessions --state Active --region us-east-1

# Stop bastion to save costs
cd backend/deploy/terraform
BASTION_ID=$(terraform output -raw bastion_instance_id)
aws ec2 stop-instances --instance-ids $BASTION_ID --region us-east-1

# Start bastion
aws ec2 start-instances --instance-ids $BASTION_ID --region us-east-1

# Get bastion status
aws ec2 describe-instances --instance-ids $BASTION_ID --region us-east-1 --query 'Reservations[0].Instances[0].State.Name' --output text
```

## Alternative: Direct SSH (If you have a key)

If you prefer traditional SSH with a key pair:

```bash
# Create tunnel with SSH
ssh -i ~/.ssh/your-key.pem -N -L 5432:RDS_ENDPOINT:5432 ec2-user@BASTION_PUBLIC_IP
```

However, SSM is recommended as it doesn't require managing SSH keys.

## Cleanup

```bash
cd backend/deploy/terraform

terraform destroy -target=aws_instance.bastion \
  -target=aws_security_group.bastion \
  -target=aws_security_group_rule.rds_from_bastion \
  -target=aws_iam_role.bastion \
  -target=aws_iam_role_policy_attachment.bastion_ssm \
  -target=aws_iam_instance_profile.bastion
```

## Support

For issues:
1. Check CloudWatch Logs: `/aws/ssm/session-logs`
2. Verify IAM permissions for SSM
3. Ensure bastion security group allows egress to RDS
4. Check RDS security group allows ingress from bastion

---

**Last Updated:** December 2024  
**Terraform Version:** 1.5+  
**AWS Region:** us-east-1  
**Project:** Docu-CR Backend
