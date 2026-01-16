#!/bin/bash

set -e

echo "Creating docucr schema in RDS..."

# Extract connection details from .env
DB_HOST="marvelsync-ivr-ocr-staging-v2.ciuwqp3kuxas.ap-south-1.rds.amazonaws.com"
DB_PORT="5432"
DB_NAME="flowcraft_db"
DB_USER="ivrocrstaging"
DB_PASSWORD="marvel#2025"

# Execute SQL script
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f create_schema.sql

echo "Schema 'docucr' created successfully!"
