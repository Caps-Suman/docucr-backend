#!/bin/bash

# Setup AWS Secrets Manager secret for application configuration
# Usage: ./setup_secrets.sh

SECRET_NAME="docu-cr/app"

echo "Creating AWS Secrets Manager secret: $SECRET_NAME"

# Create the secret with all required fields
aws secretsmanager create-secret \
  --name "$SECRET_NAME" \
  --description "Application secrets for Docu-CR backend" \
  --secret-string '{
    "SECRET_KEY": "your-secret-key-here-change-me",
    "JWT_SECRET_KEY": "your-jwt-secret-key-here-change-me",
    "ADMIN_PASSWORD": "Admin@2025",
    "AWS_S3_BUCKET": "your-s3-bucket-name",
    "AWS_ACCESS_KEY_ID": "your-aws-access-key-id",
    "AWS_SECRET_ACCESS_KEY": "your-aws-secret-access-key"
  }' 2>&1

if [ $? -eq 0 ]; then
  echo "✓ Secret created successfully"
  echo ""
  echo "IMPORTANT: Update the secret values with your actual credentials:"
  echo "  aws secretsmanager update-secret --secret-id $SECRET_NAME --secret-string '{...}'"
else
  echo "✗ Failed to create secret (it may already exist)"
  echo ""
  echo "To update existing secret, run:"
  echo "  aws secretsmanager update-secret --secret-id $SECRET_NAME --secret-string '{...}'"
fi
