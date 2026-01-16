# Database credentials
resource "aws_secretsmanager_secret" "db_credentials" {
  name = "${var.project_name}/rds"
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = aws_db_instance.postgres.username
    password = aws_db_instance.postgres.password
  })
}

# Database URL secret
resource "aws_secretsmanager_secret" "database_url" {
  name = "${var.project_name}/database-url"
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql://${aws_db_instance.postgres.username}:${aws_db_instance.postgres.password}@${aws_db_instance.postgres.address}:5432/${aws_db_instance.postgres.db_name}"
}

# Import existing secrets
data "aws_secretsmanager_secret" "app" {
  name = "${var.project_name}/app"
}
