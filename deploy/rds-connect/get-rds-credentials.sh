#!/bin/bash
# Get RDS Credentials
# Retrieves database credentials from Terraform outputs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../terraform"

DB_USER=$(terraform output -raw db_username 2>/dev/null || echo "")
DB_PASS=$(terraform output -raw db_password 2>/dev/null || echo "")
DB_NAME=$(terraform output -raw db_name 2>/dev/null || echo "")
RDS_ENDPOINT=$(terraform output -raw rds_endpoint 2>/dev/null || echo "")

if [ -z "$DB_USER" ]; then
    echo "❌ Error: Could not retrieve database credentials"
    echo "Run 'terraform apply' first"
    exit 1
fi

echo "📊 RDS Database Credentials"
echo "============================"
echo ""
echo "Host:     $(echo $RDS_ENDPOINT | cut -d: -f1)"
echo "Port:     5432 (via tunnel: localhost:5344)"
echo "Database: $DB_NAME"
echo "Username: $DB_USER"
echo "Password: $DB_PASS"
echo ""
echo "💡 Copy the password above for DBeaver"
