import os
from dotenv import load_dotenv

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "local")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Local document directory for BM25 index
_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS_DIR = os.getenv("DOCS_DIR", os.path.join(_HERE, "data", "raw", "osha_documents"))

# AWS
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# BM25 search tuning
BEDROCK_RETRIEVAL_TOP_K = int(os.getenv("BEDROCK_RETRIEVAL_TOP_K", "5"))
BEDROCK_RETRIEVAL_MIN_SCORE = float(os.getenv("BEDROCK_RETRIEVAL_MIN_SCORE", "0.3"))

# Bedrock LLM
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-sonnet-20240229-v1:0")
BEDROCK_TEMPERATURE = float(os.getenv("BEDROCK_TEMPERATURE", "0.1"))
BEDROCK_MAX_TOKENS = int(os.getenv("BEDROCK_MAX_TOKENS", "4096"))

# DynamoDB
DYNAMODB_REGION = os.getenv("DYNAMODB_REGION", "us-east-1")
DYNAMODB_ENDPOINT = os.getenv("DYNAMODB_ENDPOINT", None)  # None = real AWS, set for local Docker
DYNAMODB_TABLE_CLIENTS = os.getenv("DYNAMODB_TABLE_CLIENTS", "osha_clients")
DYNAMODB_TABLE_AGENTS = os.getenv("DYNAMODB_TABLE_AGENTS", "osha_agents")
DYNAMODB_TABLE_API_KEYS = os.getenv("DYNAMODB_TABLE_API_KEYS", "osha_api_keys")
DYNAMODB_TABLE_QUERY_LOGS = os.getenv("DYNAMODB_TABLE_QUERY_LOGS", "osha_query_logs")
DYNAMODB_TABLE_SESSIONS = os.getenv("DYNAMODB_TABLE_SESSIONS", "osha_sessions")

# Session
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
SESSION_MAX_HISTORY = int(os.getenv("SESSION_MAX_HISTORY", "10"))

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_RATE_LIMIT_REQUESTS = int(os.getenv("REDIS_RATE_LIMIT_REQUESTS", "60"))
REDIS_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("REDIS_RATE_LIMIT_WINDOW_SECONDS", "60"))

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "5000"))
API_CORS_ORIGINS = os.getenv("API_CORS_ORIGINS", '["http://localhost:3000"]')
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "./logs/app.log")


def validate():
    missing = []
    if not AWS_ACCESS_KEY_ID:
        missing.append("AWS_ACCESS_KEY_ID")
    if not AWS_SECRET_ACCESS_KEY:
        missing.append("AWS_SECRET_ACCESS_KEY")
    if not ADMIN_API_KEY:
        missing.append("ADMIN_API_KEY")
    if not os.path.isdir(DOCS_DIR):
        raise EnvironmentError(f"DOCS_DIR not found: {DOCS_DIR}")
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
