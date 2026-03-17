#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# To Check Log of Servers :
# cd ..
# ./check-logs.sh        # last 200 lines
# ./check-logs.sh live   # live follow
# ./check-logs.sh ai     # AI errors only

CONTAINER="docucr-staging"
MODE="${1:-tail}"   # default: tail | options: tail, live, ai

# Get values from terraform output
cd terraform
INSTANCE_ID=$(terraform output -raw ec2_instance_id 2>/dev/null)
REGION=$(terraform output -raw aws_region 2>/dev/null || echo "us-east-1")
cd ..

if [ -z "$INSTANCE_ID" ]; then
    echo -e "${RED}❌ Could not get EC2 instance ID from terraform output${NC}"
    exit 1
fi

echo -e "${GREEN}📋 DocuCR Staging Logs — $INSTANCE_ID${NC}"
echo ""

case "$MODE" in
  live)
    echo -e "${CYAN}🔴 Live logs (Ctrl+C to stop):${NC}"
    aws ssm start-session \
      --target $INSTANCE_ID \
      --region $REGION \
      --document-name AWS-StartInteractiveCommand \
      --parameters command="docker logs $CONTAINER -f --tail 50"
    ;;
  ai)
    echo -e "${CYAN}🤖 AI service logs (last 200 lines, filtered):${NC}"
    aws ssm send-command \
      --instance-ids $INSTANCE_ID \
      --region $REGION \
      --document-name "AWS-RunShellScript" \
      --parameters "commands=[\"docker logs $CONTAINER 2>&1 | grep -i 'ai_service\\|ai_failed\\|openai\\|analyze_document\\|error\\|exception' | tail -200\"]" \
      --output text \
      --query "Command.CommandId" | xargs -I {} sh -c '
        sleep 3
        aws ssm get-command-invocation \
          --command-id {} \
          --instance-id '$INSTANCE_ID' \
          --region '$REGION' \
          --query "StandardOutputContent" \
          --output text'
    ;;
  tail|*)
    echo -e "${CYAN}📝 Last 200 lines:${NC}"
    aws ssm send-command \
      --instance-ids $INSTANCE_ID \
      --region $REGION \
      --document-name "AWS-RunShellScript" \
      --parameters "commands=[\"docker logs $CONTAINER 2>&1 | tail -200\"]" \
      --output text \
      --query "Command.CommandId" | xargs -I {} sh -c '
        sleep 3
        aws ssm get-command-invocation \
          --command-id {} \
          --instance-id '$INSTANCE_ID' \
          --region '$REGION' \
          --query "StandardOutputContent" \
          --output text'
    ;;
esac
