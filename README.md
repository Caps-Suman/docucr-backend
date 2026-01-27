# docucr Backend

PaaS-ready backend for docucr document processing platform.

## Project Structure

```
backend/
├── alembic/              # Database migrations
├── app/
│   ├── core/            # Config, Security, Database
│   ├── models/          # SQLModel/SQLAlchemy Models
│   ├── routers/         # API Endpoints (Controllers)
│   ├── services/        # Business Logic & Integrations
│   ├── templates/       # HTML Templates (Email/Pages)
│   └── utils/           # Shared Utilities
├── deploy/              # Terraform & Docker configs
├── tests/               # Pytest suites
├── app.py               # Main entry point
└── requirements.txt     # Dependencies
```

## Functional Modules

The backend is organized into several key domains:

- **Core & IAM**: Authentication, User Management, Role-Based Access Control (RBAC), Modules.
- **Document Management**: Document Upload, Type Management, Template Configuration, Sharing (Internal/External).
- **Automation & AI**:
    - **OCR/Extraction**: Automated data extraction using Azure OpenAI / Custom Models.
    - **Form Processing**: Dynamic form schema generation and validation.
- **Workflow**: Status Management, SOP (Standard Operating Procedures) enforcement, Webhooks.
- **Real-time**: Websocket support for live updates (Dashboard/Notifications).

## Architecture & Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Database**: PostgreSQL + SQLAlchemy (Async)
- **Migrations**: Alembic
- **Auth**: JWT (JSON Web Tokens)
- **Integrations**:
    - **AWS S3**: Secure document storage.
    - **Azure OpenAI**: Intelligence layer for document analysis.
    - **WebSockets**: Real-time event broadcasting.
- **Testing**: Pytest

## Key Development Commands

### 1. Run Application
```bash
# Standard run (Auto-reload enabled in app.py or use uvicorn directly)
python app.py

# OR using uvicorn directly
uvicorn app.main:app --reload
```

### 2. Run Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_auth_router.py
```

### 3. Database Utility Scripts
The root directory contains helper scripts for database management:
```bash
# Seed the database with initial submodules/roles
python run_seed.py

# Sync master data (if applicable)
python sync_master_data.py

# Generate a new secure JWT secret
python generate_jwt_secret.py
```

## Database Setup

### Database Configuration
- **Database**: `docucr_db`
- **Schema**: `docucr`
- **RDS Endpoint**: `<your-rds-endpoint>`



## Alembic Migrations

### 1. Initialize/Generate Migration
To generate a new migration file after modifying models:
```bash
# Ensure you are exporting the correct schema
export DB_SCHEMA='docucr'
alembic revision --autogenerate -m "Describe your change"
```

### 2. Apply Migrations
To apply pending migrations to the database:
```bash
alembic upgrade head
```

### 3. Verify Database Status
To check if the database is up-to-date with the code:
```bash
alembic check
```
*Returns exit code 0 if synced, non-zero if drift is detected.*

### 4. Resetting/Stamping (Critical)
If you are setting up a new environment or fixing synchronization issues where the schema already exists but the migration history is missing:

**DO NOT run `upgrade head` if the tables already exist.**

Instead, "stamp" the database to the current head revision:
```bash
# Get the current head revision ID
alembic heads

# Stamp the database (mark it as up-to-date without running SQL)
alembic stamp <revision_id>
# OR simply
alembic stamp head
```

### 5. View History
```bash
alembic history
```

## Local Development

### 1. Setup Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate (Mac/Linux)
source venv/bin/activate

# Activate (Windows)
.\venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Application
```bash
python app.py
```

## Docker Deployment

### Build Image
```bash
docker build -t docucr-backend .
```

### Run Container
```bash
docker run -p 5000:5000 --env-file .env docucr-backend
```
> **Note**: The Docker container installs dependencies globally. No virtual environment (`venv`) activation is required inside the container.

## AWS Deployment

See [deploy/TERRAFORM-README.md](deploy/TERRAFORM-README.md) for infrastructure deployment.

### Deployment Scripts

The `deploy/` directory contains helper scripts to streamline AWS deployment:

#### 1. Setup Secrets
Updates AWS Secrets Manager with your application credentials.
```bash
# Usage: ./deploy/setup-secrets.sh <region>
./deploy/setup-secrets.sh us-east-1
```
*Prompts for: App Secret Key, JWT Secret, Admin Password.*

#### 2. Deploy Application
Builds the Docker image, pushes to ECR, and forces a new deployment on ECS.
```bash
cd deploy
./deploy.sh
```
*Prerequisites: AWS CLI configured with appropriate permissions.*

### Running Migrations on ECS

Since ECS runs containers, you cannot directly access the shell. Use **ECS Exec** to run migrations safely.

1.  **Enable ECS Exec** (if not already):
    ```bash
    aws ecs update-service --cluster <cluster-name> --service <service-name> --enable-execute-command
    ```

2.  **Get Task ID**:
    ```bash
    aws ecs list-tasks --cluster <cluster-name> --service-name <service-name>
    ```

3.  **Execute Migration**:
    ```bash
    aws ecs execute-command --cluster <cluster-name> \
        --task <task-id> \
        --container docucr-backend \
        --interactive \
        --command "alembic upgrade head"
    ```
    *Note: If you need to debug, change the command to `/bin/bash` to get a shell.*

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
DATABASE_URL=postgresql://user:pass@host:5432/docucr_db
DB_SCHEMA=docucr
JWT_SECRET_KEY=your_secure_secret
FRONTEND_URL=http://localhost:4200

# AWS Settings
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_REGION=us-east-1
AWS_S3_BUCKET=docucr-resource

# Azure OpenAI
AZURE_OPENAI_API_KEY=xxx
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-xx-xx

# OpenAI (Fallback/Alternative)
OPENAI_API_KEY=sk-xxx

# Email (SMTP)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@example.com
SMTP_PASSWORD=your-app-password
SENDER_EMAIL=your-email@example.com
```

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:5000/docs`
- ReDoc: `http://localhost:5000/redoc`
