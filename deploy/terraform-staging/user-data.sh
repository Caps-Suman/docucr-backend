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

# Create docker-compose template
cat > /home/ec2-user/app/docker-compose.yml.template << 'COMPOSE_EOF'
version: '3.8'

services:
  backend:
    image: YOUR_IMAGE_HERE
    container_name: ${app_name}
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://USER:PASS@HOST:5432/DB
      - DB_SCHEMA=docucr
      - ENVIRONMENT=staging
      - PORT=8000
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
COMPOSE_EOF

chown ec2-user:ec2-user /home/ec2-user/app/docker-compose.yml.template

# Create nginx config template
cat > /etc/nginx/conf.d/app.conf.template << 'NGINX_EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 100M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /health {
        proxy_pass http://localhost:8000/health;
        access_log off;
    }
}
NGINX_EOF

# Create deployment script
cat > /home/ec2-user/deploy.sh << 'DEPLOY_EOF'
#!/bin/bash
set -e

cd /home/ec2-user/app

echo "Pulling latest image..."
docker-compose pull

echo "Stopping old containers..."
docker-compose down

echo "Starting new containers..."
docker-compose up -d

echo "Deployment complete!"
docker-compose ps
DEPLOY_EOF

chmod +x /home/ec2-user/deploy.sh
chown ec2-user:ec2-user /home/ec2-user/deploy.sh

# Create setup completion marker
echo "Setup completed at $(date)" > /home/ec2-user/setup-complete.txt
echo "Docker version: $(docker --version)" >> /home/ec2-user/setup-complete.txt
echo "Docker Compose version: $(docker-compose --version)" >> /home/ec2-user/setup-complete.txt

echo "Setup complete!"
