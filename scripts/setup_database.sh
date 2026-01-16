#!/bin/bash

set -e

echo "Creating docucr_db database in RDS..."

DB_HOST="marvelsync-ivr-ocr-staging-v2.ciuwqp3kuxas.ap-south-1.rds.amazonaws.com"
DB_PORT="5432"
DB_USER="ivrocrstaging"
DB_PASSWORD="marvel#2025"

PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -f create_database.sql

echo "Database 'docucr_db' created successfully!"
