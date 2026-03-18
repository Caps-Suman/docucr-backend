# Terraform Commands Reference

## Initial Setup (New Infrastructure)

### 1. Initialize Terraform
```bash
cd deploy/terraform-staging
terraform init
```
**Purpose**: Downloads providers (AWS, Random), initializes backend

### 2. Validate Configuration
```bash
terraform validate
```
**Purpose**: Checks syntax and configuration errors

### 3. Format Code
```bash
terraform fmt -recursive
```
**Purpose**: Auto-formats all .tf files

### 4. Create terraform.tfvars
```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 5. Plan Infrastructure
```bash
terraform plan
```
**Purpose**: Preview what will be created (dry-run)

### 6. Create Infrastructure
```bash
terraform apply
# Or auto-approve:
terraform apply -auto-approve
```
**Purpose**: Creates all AWS resources

---

## Managing Existing Infrastructure

### View Current State
```bash
# Show all resources
terraform state list

# Show specific resource details
terraform state show aws_instance.staging
terraform state show aws_db_instance.staging

# View all outputs
terraform output

# View specific output
terraform output ec2_public_ip
terraform output -raw database_url
```

### Refresh State
```bash
# Sync state with actual AWS resources
terraform refresh
```

### Check for Changes
```bash
# See what would change
terraform plan

# Save plan to file
terraform plan -out=tfplan

# Apply saved plan
terraform apply tfplan
```

### Update Specific Resource
```bash
# Target specific resource
terraform apply -target=aws_instance.staging
terraform apply -target=aws_db_instance.staging
```

### View Resource Details
```bash
# Show resource configuration
terraform show

# Show in JSON format
terraform show -json | jq
```

---

## Modifying Infrastructure

### Update Variables
```bash
# 1. Edit terraform.tfvars or variables.tf
nano terraform.tfvars

# 2. Plan changes
terraform plan

# 3. Apply changes
terraform apply
```

### Common Updates

**Upgrade EC2 Instance Type:**
```bash
# Edit terraform.tfvars
instance_type = "t3.small"

terraform apply
```

**Upgrade RDS Instance:**
```bash
# Edit terraform.tfvars
db_instance_class = "db.t3.small"

terraform apply
```

**Change Backup Retention:**
```bash
# Edit terraform.tfvars
db_backup_retention_period = 5

terraform apply
```

---

## Troubleshooting

### Fix State Issues
```bash
# If state is out of sync
terraform refresh

# Import existing resource
terraform import aws_instance.staging i-xxxxx

# Remove resource from state (doesn't delete)
terraform state rm aws_instance.staging
```

### Unlock State
```bash
# If state is locked
terraform force-unlock <LOCK_ID>
```

### Taint Resource (Force Recreate)
```bash
# Mark resource for recreation
terraform taint aws_instance.staging

# Apply to recreate
terraform apply
```

### Untaint Resource
```bash
terraform untaint aws_instance.staging
```

---

## Destroying Infrastructure

### Destroy Everything
```bash
# Preview what will be destroyed
terraform plan -destroy

# Destroy all resources
terraform destroy

# Auto-approve destruction
terraform destroy -auto-approve
```

### Destroy Specific Resource
```bash
terraform destroy -target=aws_instance.staging
```

---

## Advanced Commands

### Workspace Management
```bash
# List workspaces
terraform workspace list

# Create new workspace
terraform workspace new production

# Switch workspace
terraform workspace select staging
```

### Graph Visualization
```bash
# Generate dependency graph
terraform graph | dot -Tpng > graph.png
```

### Console (Test Expressions)
```bash
terraform console
> var.project_name
> aws_instance.staging.public_ip
```

### Import Existing Resources
```bash
# Import EC2 instance
terraform import aws_instance.staging i-03f2d7fdc7d3287fa

# Import RDS instance
terraform import aws_db_instance.staging docucr-staging-db
```

---

## Useful Workflows

### Daily Operations

**Check Infrastructure Status:**
```bash
terraform refresh
terraform output
```

**Apply Configuration Changes:**
```bash
terraform plan
terraform apply
```

**View Logs:**
```bash
# Enable detailed logging
export TF_LOG=DEBUG
terraform apply

# Save logs to file
export TF_LOG_PATH=./terraform.log
```

### Before Making Changes

```bash
# 1. Backup state
cp terraform.tfstate terraform.tfstate.backup.$(date +%Y%m%d)

# 2. Plan changes
terraform plan -out=tfplan

# 3. Review plan
terraform show tfplan

# 4. Apply if looks good
terraform apply tfplan
```

### Rollback Changes

```bash
# If you have a backup state file
cp terraform.tfstate.backup terraform.tfstate
terraform refresh
```

---

## Environment-Specific Commands

### Staging Environment
```bash
cd deploy/terraform-staging

# Create/Update
terraform apply

# View outputs
terraform output

# Destroy
terraform destroy
```

### Production Environment
```bash
cd deploy/terraform

# Create/Update
terraform apply

# View outputs
terraform output

# Destroy
terraform destroy
```

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `terraform init` | Initialize working directory |
| `terraform validate` | Validate configuration |
| `terraform fmt` | Format code |
| `terraform plan` | Preview changes |
| `terraform apply` | Create/update resources |
| `terraform destroy` | Delete resources |
| `terraform output` | Show outputs |
| `terraform state list` | List resources |
| `terraform refresh` | Sync state with AWS |
| `terraform show` | Show current state |

---

## Common Issues & Solutions

**Issue: State locked**
```bash
terraform force-unlock <LOCK_ID>
```

**Issue: Resource already exists**
```bash
terraform import <resource_type>.<name> <resource_id>
```

**Issue: State out of sync**
```bash
terraform refresh
```

**Issue: Want to recreate resource**
```bash
terraform taint <resource>
terraform apply
```

**Issue: Need to see detailed logs**
```bash
export TF_LOG=DEBUG
terraform apply
```

---

## Best Practices

1. **Always run `terraform plan` before `apply`**
2. **Backup state files before major changes**
3. **Use version control for .tf files**
4. **Never commit terraform.tfvars with secrets**
5. **Use `-target` for surgical updates**
6. **Review outputs after apply**
7. **Document changes in git commits**
8. **Test in staging before production**

---

## Files to Version Control

✅ **Commit these:**
- `*.tf` files
- `terraform.tfvars.example`
- `.terraform.lock.hcl`

❌ **Never commit:**
- `terraform.tfstate*`
- `terraform.tfvars` (contains secrets)
- `.terraform/` directory
- `*.tfplan` files
