#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🔌 Testing WebSocket Connection${NC}"
echo ""

# Test WebSocket using websocat (if available) or curl
echo -e "${YELLOW}Testing WSS endpoint...${NC}"

# Check if backend is running
echo -e "${YELLOW}1. Checking backend health:${NC}"
curl -s https://docucrapi.medeye360.com/health || echo -e "${RED}Backend not responding${NC}"
echo ""

# Check Nginx WebSocket headers
echo -e "${YELLOW}2. Checking Nginx WebSocket configuration:${NC}"
ssh -i ~/Documents/fhrm/fhrm-pem-key/ivr-staging-key.pem ec2-user@18.211.1.245 "sudo nginx -t" 2>&1 | grep -i "successful" && echo -e "${GREEN}✅ Nginx config valid${NC}" || echo -e "${RED}❌ Nginx config invalid${NC}"
echo ""

# Check if WebSocket upgrade headers are configured
echo -e "${YELLOW}3. Verifying WebSocket headers in Nginx:${NC}"
ssh -i ~/Documents/fhrm/fhrm-pem-key/ivr-staging-key.pem ec2-user@18.211.1.245 "sudo grep -A 5 'WebSocket' /etc/nginx/conf.d/backend.conf" && echo -e "${GREEN}✅ WebSocket headers configured${NC}" || echo -e "${RED}❌ WebSocket headers missing${NC}"
echo ""

echo -e "${YELLOW}4. Test from browser console:${NC}"
echo "const ws = new WebSocket('wss://docucrapi.medeye360.com/api/documents/ws/test-id');"
echo "ws.onopen = () => console.log('✅ Connected');"
echo "ws.onerror = (e) => console.log('❌ Error:', e);"
