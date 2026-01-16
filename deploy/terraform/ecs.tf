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
          value = "aiicr"
        },

        {
          name  = "ADMIN_EMAIL"
          value = "admin@aiicr.com"
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
          name      = "SECRET_KEY"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:SECRET_KEY::"
        },
        {
          name      = "JWT_SECRET_KEY"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:JWT_SECRET_KEY::"
        },
        {
          name      = "ADMIN_PASSWORD"
          valueFrom = "${data.aws_secretsmanager_secret.app.arn}:ADMIN_PASSWORD::"
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
        }
      ]
      
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
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

  depends_on = [aws_lb_listener.app]
}