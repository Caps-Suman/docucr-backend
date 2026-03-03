#!/bin/bash

# Setup AWS Secrets Manager secrets
# Usage: ./deploy/setup-secrets.sh <region>

set -e

if [ $# -lt 1 ]; then
    echo "Usage: $0 <region>"
    echo "Example: $0 us-east-1"
    exit 1
fi

REGION=$1
PROJECT_NAME="docu-cr-backend"

echo "Setting up secrets in region: $REGION"

# Function to create or update secret
create_or_update_secret() {
    local secret_name=$1
    local secret_value=$2
    
    if aws secretsmanager describe-secret --secret-id "$secret_name" --region "$REGION" >/dev/null 2>&1; then
        echo "Updating existing secret: $secret_name"
        aws secretsmanager update-secret \
            --secret-id "$secret_name" \
            --secret-string "$secret_value" \
            --region "$REGION"
    else
        echo "Creating new secret: $secret_name"
        aws secretsmanager create-secret \
            --name "$secret_name" \
            --secret-string "$secret_value" \
            --region "$REGION"
    fi
}

# Prompt for secrets
echo "Enter your application credentials:"

read -p "Application Secret Key (32+ chars): " SECRET_KEY
read -p "JWT Secret Key (32+ chars): " JWT_SECRET_KEY
read -p "Admin Password (default: AIICR2025!): " ADMIN_PASSWORD
ADMIN_PASSWORD=${ADMIN_PASSWORD:-AIICR2025!}

# Create secrets
create_or_update_secret "${PROJECT_NAME}/app" "{
    \"SECRET_KEY\": \"$SECRET_KEY\",
    \"JWT_SECRET_KEY\": \"$JWT_SECRET_KEY\",
    \"ADMIN_PASSWORD\": \"$ADMIN_PASSWORD\"
}"

echo "All secrets have been created/updated successfully!"