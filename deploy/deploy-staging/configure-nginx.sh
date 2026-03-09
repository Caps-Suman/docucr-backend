#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🔧 Configuring Nginx for WebSocket support${NC}"
echo ""

# Get EC2 IP from Terraform
cd terraform
EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null || echo "")
cd ..

if [ -z "$EC2_IP" ]; then
    echo -e "${RED}❌ Could not retrieve EC2 IP${NC}"
    exit 1
fi

echo -e "${YELLOW}Target EC2: $EC2_IP${NC}"

# Copy Nginx config to EC2
echo -e "${GREEN}📝 Uploading Nginx configuration...${NC}"
scp -o StrictHostKeyChecking=no -i ~/.ssh/docu-cr-backend-key.pem nginx-backend.conf ec2-user@$EC2_IP:/tmp/backend.conf

# Configure Nginx on EC2
echo -e "${GREEN}🔧 Applying Nginx configuration...${NC}"
ssh -o StrictHostKeyChecking=no -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP << 'ENDSSH'
  # Create WebSocket map config
  sudo tee /etc/nginx/conf.d/websocket-map.conf > /dev/null << 'EOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}
EOF
  
  sudo mv /tmp/backend.conf /etc/nginx/conf.d/backend.conf
  sudo rm -f /etc/nginx/conf.d/app.conf
  sudo nginx -t && sudo systemctl reload nginx
  echo "✅ Nginx configured successfully"
ENDSSH

echo ""
echo -e "${GREEN}✅ Nginx configuration complete!${NC}"
