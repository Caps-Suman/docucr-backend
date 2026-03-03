#!/bin/bash
set -e

# Log everything
exec > >(tee /var/log/user-data.log)
exec 2>&1

echo "Starting setup for ${app_name}..."

# Update system
yum update -y

# Install Docker
yum install -y docker
systemctl start docker
systemctl enable docker
usermod -aG docker ec2-user

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

# Install Git
yum install -y git

# Install Nginx
yum install -y nginx
systemctl enable nginx

# Install Certbot for SSL
yum install -y certbot python3-certbot-nginx

# Install PostgreSQL client
yum install -y postgresql15

# Create app directory
mkdir -p /home/ec2-user/app
chown -R ec2-user:ec2-user /home/ec2-user/app

# Configure Nginx with WebSocket support
if [ -n "${domain}" ]; then
  cat > /etc/nginx/conf.d/app.conf << 'NGINX'
server {
    listen 80;
    server_name ${domain};

    client_max_body_size 100M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    location /health {
        proxy_pass http://localhost:8000/health;
        access_log off;
    }
}
NGINX

  systemctl restart nginx
  
  # Wait for nginx to start
  sleep 5
  
  # Install SSL certificate
  certbot --nginx -d ${domain} --non-interactive --agree-tos --register-unsafely-without-email --redirect || echo "SSL setup will be done manually"
fi

# Create setup completion marker
echo "Setup completed at $(date)" > /home/ec2-user/setup-complete.txt
echo "Docker version: $(docker --version)" >> /home/ec2-user/setup-complete.txt
echo "Docker Compose version: $(docker-compose --version)" >> /home/ec2-user/setup-complete.txt
if [ -n "${domain}" ]; then
  echo "Domain: ${domain}" >> /home/ec2-user/setup-complete.txt
  echo "SSL: Configured" >> /home/ec2-user/setup-complete.txt
fi

echo "Setup complete!"
