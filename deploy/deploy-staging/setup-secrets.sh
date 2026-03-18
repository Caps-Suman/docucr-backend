#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🔐 Setting up Staging Secrets${NC}"
echo ""

PROD_SECRET="docu-cr-backend/app"
STAGING_SECRET="docucr-staging/app"
REGION="us-east-1"

# Fetch production secrets
echo -e "${GREEN}📥 Fetching production secrets...${NC}"
PROD_SECRETS=$(aws secretsmanager get-secret-value --secret-id $PROD_SECRET --region $REGION --query SecretString --output text)

if [ -z "$PROD_SECRETS" ]; then
    echo -e "${RED}❌ Failed to fetch production secrets${NC}"
    exit 1
fi

# Check if staging secret already exists
echo -e "${GREEN}🔍 Checking if staging secret exists...${NC}"
if aws secretsmanager describe-secret --secret-id $STAGING_SECRET --region $REGION 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Staging secret already exists. Updating...${NC}"
    aws secretsmanager update-secret \
        --secret-id $STAGING_SECRET \
        --secret-string "$PROD_SECRETS" \
        --region $REGION
    echo -e "${GREEN}✅ Staging secret updated${NC}"
else
    echo -e "${GREEN}📝 Creating new staging secret...${NC}"
    aws secretsmanager create-secret \
        --name $STAGING_SECRET \
        --description "Staging environment secrets for DocuCR Backend" \
        --secret-string "$PROD_SECRETS" \
        --region $REGION \
        --tags Key=Environment,Value=staging Key=Project,Value=docucr-staging
    echo -e "${GREEN}✅ Staging secret created${NC}"
fi

echo ""
echo -e "${GREEN}✅ Secrets setup complete!${NC}"
echo -e "${YELLOW}Secret name: $STAGING_SECRET${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Update terraform.tfvars: secrets_name = \"$STAGING_SECRET\""
echo -e "2. Run: terraform apply"
echo -e "3. Update deploy.sh to fetch secrets from Secrets Manager"
