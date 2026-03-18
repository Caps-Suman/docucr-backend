# ECS Task Definition
resource "aws_ecs_task_definition" "app" {
  family                   = var.project_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn           = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = var.project_name
      image = var.container_image
      
      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]
      
      essential = true
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
      
      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        {
          name  = "PORT"
          value = "8000"
        },
        {
          name  = "DEBUG"
          value = "false"
        },
        {
          name  = "RDS_HOST"
          value = aws_db_instance.postgres.address
        },
        {
          name  = "RDS_PORT"
          value = "5432"
        },
        {
          name  = "RDS_NAME"
          value = aws_db_instance.postgres.db_name
        },
        {
          name  = "DB_SCHEMA"
          value = "docucr"
        },
        {
          name  = "AZURE_OPENAI_ENDPOINT"
          value = "https://customer-service-agents-resource.cognitiveservices.azure.com/"
        },
        {
          name  = "AZURE_OPENAI_DEPLOYMENT_NAME"
          value = "gpt-4o-mini"
        },
        {
          name  = "AZURE_OPENAI_API_VERSION"
          value = "2024-12-01-preview"
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "SMTP_PORT"
          value = "587"
        },
        {
          name  = "SMTP_SERVER"
          value = "smtp.gmail.com"
        },
        {
          name  = "FRONTEND_URL"
          value = "https://docucr.medeye360.com"
        },
        {
          name  = "ADMIN_EMAIL"
          value = "suman.singh@marvelsync.com"
        },
        {
          name  = "ALLOWED_HOSTS"
          value = "*"
        }
      ]
      
      secrets = [
        {
          name      = "RDS_USERNAME"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:username::"
        },
        {
          name      = "RDS_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.db_credentials.arn}:password::"
        },
        {
          name      = "DATABASE_URL"
          valueFrom = aws_secretsmanager_secret.database_url.arn
        },
        {
          name      = "JWT_SECRET_KEY"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:JWT_SECRET_KEY::"
        },
        {
          name      = "AWS_S3_BUCKET"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:AWS_S3_BUCKET::"
        },
        {
          name      = "AWS_ACCESS_KEY_ID"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:AWS_ACCESS_KEY_ID::"
        },
        {
          name      = "AWS_SECRET_ACCESS_KEY"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:AWS_SECRET_ACCESS_KEY::"
        },
        {
          name      = "AZURE_OPENAI_API_KEY"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:AZURE_OPENAI_API_KEY::"
        },
        {
          name      = "SMTP_USERNAME"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:SMTP_USERNAME::"
        },
        {
          name      = "SMTP_PASSWORD"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:SMTP_PASSWORD::"
        },
        {
          name      = "SENDER_EMAIL"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:SENDER_EMAIL::"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:OPENAI_API_KEY::"
        }
      ]
      
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import requests; requests.get('http://localhost:8000/health')\" || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 120
      }
    }
  ])
}

# ECS Service
resource "aws_ecs_service" "app" {
  name            = "${var.project_name}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    security_groups  = [aws_security_group.ecs.id]
    subnets         = [aws_subnet.private.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = var.project_name
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.app, aws_lb_listener.app_https]
}