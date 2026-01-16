# NAT Instance (Cost-effective alternative to NAT Gateway)

# Get latest Amazon Linux 2 AMI
data "aws_ami" "amazon_linux_2" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

# Security Group for NAT Instance
resource "aws_security_group" "nat_instance" {
  name_prefix = "${var.project_name}-nat-instance-"
  vpc_id      = aws_vpc.main.id

  # Allow SSH from anywhere
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH access"
  }

  # Allow all traffic from VPC
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.0.0.0/16"]
    description = "Allow all traffic from VPC"
  }

  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-nat-instance-sg"
  }
}

# NAT Instance
resource "aws_instance" "nat_instance" {
  ami                         = data.aws_ami.amazon_linux_2.id
  instance_type               = "t3.nano"
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.nat_instance.id]
  key_name                    = aws_key_pair.main.key_name
  associate_public_ip_address = true
  source_dest_check           = false

  user_data = <<-EOF
    #!/bin/bash
    yum install -y iptables-services
    systemctl enable iptables
    systemctl start iptables
    echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
    sysctl -p
    iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
    iptables -F FORWARD
    iptables -A FORWARD -i eth0 -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT
    iptables -A FORWARD -i eth0 -o eth0 -j ACCEPT
    service iptables save
  EOF

  tags = {
    Name = "${var.project_name}-nat-instance"
  }
}

# Elastic IP for NAT Instance
resource "aws_eip" "nat_instance" {
  domain   = "vpc"
  instance = aws_instance.nat_instance.id

  tags = {
    Name = "${var.project_name}-nat-instance-eip"
  }

  depends_on = [aws_internet_gateway.main]
}
