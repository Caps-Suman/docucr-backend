# docucr Backend

PaaS-ready backend for docucr document processing platform.

## Project Structure

```
backend/
├── alembic/              # Database migrations
├── app/
│   ├── api/             # API endpoints
│   ├── core/            # Core configurations
│   ├── models/          # Database models
│   ├── services/        # Business logic
│   └── utils/           # Utility functions
├── deploy/              # Deployment configurations
│   ├── terraform/       # AWS infrastructure
│   └── rds-connect/     # RDS connection scripts
├── exports/             # Export files
├── logs/                # Application logs
├── models/              # ML models
├── scripts/             # Utility scripts
├── uploads/             # File uploads
├── app.py               # Application entry point
├── Dockerfile           # Container configuration
└── requirements.txt     # Python dependencies
```

## Database Setup

### Database Configuration
- **Database**: `docucr_db`
- **Schema**: `docucr`
- **RDS Endpoint**: `marvelsync-ivr-ocr-staging-v2.ciuwqp3kuxas.ap-south-1.rds.amazonaws.com`

### Create Database
```bash
cd scripts
./setup_database.sh
```

## Alembic Migrations

### Initialize Migration
```bash
alembic revision --autogenerate -m "Initial migration"
```

### Apply Migrations
```bash
alembic upgrade head
```

### Rollback Migration
```bash
alembic downgrade -1
```

### View Migration History
```bash
alembic history
```

## Local Development

### Install Dependencies
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

## AWS Deployment

See [deploy/TERRAFORM-README.md](deploy/TERRAFORM-README.md) for infrastructure deployment.

### Quick Deploy
```bash
cd deploy
./deploy.sh
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
DATABASE_URL=postgresql://user:pass@host:5432/docucr_db
DB_SCHEMA=docucr
AWS_REGION=us-east-1
AWS_S3_BUCKET=docucr-resource
```

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:5000/docs`
- ReDoc: `http://localhost:5000/redoc`
