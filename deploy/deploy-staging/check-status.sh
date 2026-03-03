#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd terraform
EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null || echo "")
cd ..

if [ -z "$EC2_IP" ]; then
    echo -e "${RED}❌ Could not get EC2 IP${NC}"
    exit 1
fi

echo -e "${GREEN}📊 Checking Staging Deployment Status${NC}"
echo ""

echo -e "${YELLOW}🐳 Docker Container Status:${NC}"
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP "docker ps -a | grep docucr-staging"
echo ""

echo -e "${YELLOW}📝 Recent Logs (last 20 lines):${NC}"
ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP "docker logs docucr-staging --tail 20"
echo ""

echo -e "${YELLOW}🌐 Health Check:${NC}"
curl -s https://docucrapi.medeye360.com/health || echo -e "${RED}Health check failed${NC}"
echo ""
