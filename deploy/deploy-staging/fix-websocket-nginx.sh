#!/bin/bash
set -e

cd terraform
EC2_IP=$(terraform output -raw ec2_public_ip 2>/dev/null)
cd ..

echo "🔧 Configuring Nginx with WebSocket support..."

ssh -i ~/.ssh/docu-cr-backend-key.pem ec2-user@$EC2_IP << 'ENDSSH'
sudo tee /etc/nginx/conf.d/backend.conf > /dev/null << 'EOF'
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name docucrapi.medeye360.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name docucrapi.medeye360.com;

    ssl_certificate /etc/letsencrypt/live/docucrapi.medeye360.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/docucrapi.medeye360.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 100M;

    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
EOF

sudo nginx -t && sudo systemctl reload nginx
echo "✅ Nginx configured with WebSocket support"
ENDSSH
