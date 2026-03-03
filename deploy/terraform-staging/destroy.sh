#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}🗑️  Destroying Staging Infrastructure${NC}"
echo ""
echo -e "${YELLOW}⚠️  WARNING: This will destroy all resources!${NC}"
echo ""

# Show what will be destroyed
terraform plan -destroy

echo ""
read -p "Are you SURE you want to destroy everything? (type 'destroy' to confirm): " confirm

if [ "$confirm" = "destroy" ]; then
    echo -e "${RED}💥 Destroying infrastructure...${NC}"
    terraform destroy -auto-approve
    
    echo ""
    echo -e "${GREEN}✅ Infrastructure destroyed${NC}"
    
    # Clean up
    rm -f tfplan outputs.txt
else
    echo -e "${GREEN}✅ Destruction cancelled${NC}"
fi
