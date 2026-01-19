from fastapi import APIRouter
import os

router = APIRouter(prefix="/api/test", tags=["test"])

@router.get("/env")
async def check_env_variables():
    """Check if environment variables are accessible"""
    env_vars = {
        "DATABASE_URL": "✅" if os.getenv("DATABASE_URL") else "❌",
        "DB_SCHEMA": os.getenv("DB_SCHEMA", "Not set"),
        "AZURE_OPENAI_API_KEY": "✅" if os.getenv("AZURE_OPENAI_API_KEY") else "❌",
        "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT", "Not set"),
        "AZURE_OPENAI_DEPLOYMENT_NAME": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "Not set"),
        "JWT_SECRET_KEY": "✅" if os.getenv("JWT_SECRET_KEY") else "❌",
        "AWS_ACCESS_KEY_ID": "✅" if os.getenv("AWS_ACCESS_KEY_ID") else "❌",
        "AWS_SECRET_ACCESS_KEY": "✅" if os.getenv("AWS_SECRET_ACCESS_KEY") else "❌",
        "AWS_REGION": os.getenv("AWS_REGION", "Not set"),
        "AWS_S3_BUCKET": os.getenv("AWS_S3_BUCKET", "Not set"),
        "SMTP_SERVER": os.getenv("SMTP_SERVER", "Not set"),
        "SMTP_PORT": os.getenv("SMTP_PORT", "Not set"),
        "SMTP_USERNAME": os.getenv("SMTP_USERNAME", "Not set"),
        "SMTP_PASSWORD": "✅" if os.getenv("SMTP_PASSWORD") else "❌",
        "SENDER_EMAIL": os.getenv("SENDER_EMAIL", "Not set"),
        "FRONTEND_URL": os.getenv("FRONTEND_URL", "Not set")
    }
    
    return {"environment_variables": env_vars}