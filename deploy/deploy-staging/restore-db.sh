#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🔄 Restoring Database Backup to Staging${NC}"
echo ""

# Get DB credentials from Terraform
cd terraform
DB_HOST=$(terraform output -raw rds_address)
DB_USER=$(terraform output -raw db_username)
DB_PASS=$(terraform output -raw db_password)
DB_NAME=$(terraform output -raw db_name)
cd ..

BACKUP_FILE="/Users/apple/Documents/docucr_db/dump-docucr_db-20260303.sql"

echo -e "${YELLOW}Database: $DB_HOST${NC}"
echo -e "${YELLOW}Backup: $BACKUP_FILE${NC}"
echo ""

# Set password for psql
export PGPASSWORD="$DB_PASS"

# Restore the backup
echo -e "${GREEN}📥 Restoring backup...${NC}"
/usr/local/Cellar/postgresql@15/15.17/bin/psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -f "$BACKUP_FILE"

echo ""
echo -e "${GREEN}✅ Database restore complete!${NC}"
