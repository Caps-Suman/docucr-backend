#!/bin/bash
# RDS Connection Helper Script
# Connects to RDS via SSM Session Manager (no SSH keys needed)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../terraform"

REGION="us-east-1"
BASTION_ID=$(terraform output -raw bastion_instance_id 2>/dev/null || echo "")
RDS_ENDPOINT=$(terraform output -raw rds_endpoint 2>/dev/null || echo "")
RDS_HOST=$(echo $RDS_ENDPOINT | cut -d: -f1)

if [ -z "$BASTION_ID" ]; then
    echo "❌ Error: Could not find bastion instance ID"
    echo "Run 'terraform apply' first to create the bastion host"
    exit 1
fi

echo "🔐 Connecting to RDS via AWS Systems Manager..."
echo "📍 RDS Host: $RDS_HOST"
echo "🖥️  Bastion: $BASTION_ID"
echo ""
echo "✅ Creating port forwarding tunnel..."
echo "   Local: localhost:5344 → Remote: $RDS_HOST:5432"
echo ""
echo "📝 DBeaver Connection Settings:"
echo "   Host: localhost"
echo "   Port: 5344"
echo "   Database: docucr_db"
echo "   Username: docucr_user"
echo "   Password: (retrieve with './get-rds-credentials.sh')"
echo ""
echo "Press Ctrl+C to close the tunnel"
echo ""

aws ssm start-session \
    --target "$BASTION_ID" \
    --document-name AWS-StartPortForwardingSessionToRemoteHost \
    --parameters "{\"host\":[\"$RDS_HOST\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5344\"]}" \
    --region "$REGION"
