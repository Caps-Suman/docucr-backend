# Bastion Host for RDS Access
# Uses AWS Systems Manager - No SSH keys needed!

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

# Security Group for Bastion
resource "aws_security_group" "bastion" {
  name_prefix = "${var.project_name}-bastion-"
  vpc_id      = aws_vpc.main.id

  # Allow SSH from anywhere
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH access"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-bastion-sg"
  }
}

# Allow bastion to access RDS
resource "aws_security_group_rule" "rds_from_bastion" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.bastion.id
  security_group_id        = aws_security_group.rds.id
}

# IAM Role for Bastion
resource "aws_iam_role" "bastion" {
  name = "${var.project_name}-bastion-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "bastion_ssm" {
  role       = aws_iam_role.bastion.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "bastion" {
  name = "${var.project_name}-bastion-profile"
  role = aws_iam_role.bastion.name
}

# Bastion EC2 Instance
resource "aws_instance" "bastion" {
  ami                         = data.aws_ami.amazon_linux_2023.id
  instance_type               = "t3.nano"
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.bastion.id]
  iam_instance_profile        = aws_iam_instance_profile.bastion.name
  associate_public_ip_address = true
  key_name                    = aws_key_pair.main.key_name

  user_data = <<-EOF
    #!/bin/bash
    yum update -y
    yum install -y postgresql15
  EOF

  tags = {
    Name = "${var.project_name}-bastion"
  }
}

# Outputs
output "bastion_instance_id" {
  description = "Bastion instance ID for SSM connection"
  value       = aws_instance.bastion.id
}

output "bastion_public_ip" {
  description = "Bastion public IP address"
  value       = aws_instance.bastion.public_ip
}

output "bastion_ssh_command" {
  description = "SSH command to connect to bastion"
  value       = "ssh -i ~/Documents/fhrm-pem-key/ssh-key ec2-user@${aws_instance.bastion.public_ip}"
}

output "bastion_connection_command" {
  description = "Command to connect to bastion via SSM"
  value       = "aws ssm start-session --target ${aws_instance.bastion.id} --region ${var.aws_region}"
}

output "rds_tunnel_command" {
  description = "Command to create SSH tunnel to RDS"
  value       = "ssh -i ~/Documents/fhrm-pem-key/ssh-key -L 5344:${aws_db_instance.postgres.address}:5432 ec2-user@${aws_instance.bastion.public_ip} -N"
}
