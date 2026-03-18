# General
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "docucr-staging"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "staging"
}

variable "key_name" {
  description = "SSH key pair name"
  type        = string
}

# EC2 Variables
variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "ec2_volume_size" {
  description = "EC2 root volume size in GB"
  type        = number
  default     = 30
}

# RDS Variables
variable "db_name" {
  description = "Database name"
  type        = string
  default     = "docucr_staging"
}

variable "db_username" {
  description = "Database username"
  type        = string
  default     = "docucr_staging"
}

variable "db_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.14"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.small"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "RDS max allocated storage in GB"
  type        = number
  default     = 50
}

variable "db_publicly_accessible" {
  description = "Make RDS publicly accessible"
  type        = bool
  default     = true
}

variable "db_backup_retention_period" {
  description = "RDS backup retention period in days"
  type        = number
  default     = 5
}

variable "domain_name" {
  description = "Domain name for SSL certificate (optional)"
  type        = string
  default     = ""
}

variable "secrets_name" {
  description = "AWS Secrets Manager secret name (use production secrets)"
  type        = string
  default     = "docu-cr-backend/app"
}
