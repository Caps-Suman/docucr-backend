output "ec2_public_ip" {
  description = "EC2 instance public IP"
  value       = aws_instance.staging.public_ip
}

output "ec2_instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.staging.id
}

output "rds_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.staging.endpoint
}

output "rds_address" {
  description = "RDS address"
  value       = aws_db_instance.staging.address
}

output "db_name" {
  description = "Database name"
  value       = aws_db_instance.staging.db_name
}

output "db_username" {
  description = "Database username"
  value       = aws_db_instance.staging.username
}

output "db_password" {
  description = "Database password"
  value       = nonsensitive(random_password.db_password.result)
}

output "ssh_command" {
  description = "SSH command to connect to EC2"
  value       = "ssh -i ~/.ssh/${var.key_name}.pem ec2-user@${aws_instance.staging.public_ip}"
}

output "database_url" {
  description = "Database connection URL"
  value       = "postgresql://${aws_db_instance.staging.username}:${nonsensitive(random_password.db_password.result)}@${aws_db_instance.staging.address}:5432/${aws_db_instance.staging.db_name}"
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_repository_name" {
  description = "ECR repository name"
  value       = aws_ecr_repository.backend.name
}
