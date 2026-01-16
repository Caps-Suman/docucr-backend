variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "docu-cr-backend"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "container_image" {
  description = "Docker image URI"
  type        = string
}

variable "db_username" {
  description = "Database username"
  type        = string
  default     = "aiicr_user"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "aiicr"
}

variable "db_schema" {
  description = "Database schema"
  type        = string
  default     = "aiicr"
}