import os 
from dotenv import load_dotenv

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "local")
DEBUG = os.getenv("DEBUG", "false").lower == "true"

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
BEDROCK_MAX_TOKENS = int(os.getenv("BEDROCK_MAX_TOKENS", "2000"))

# S3
S3_BUCKET = os.getenv("S3_BUCKET")
S3_PREFIX = os.getenv("S3_PREFIX", "osha_documents")

# DynamoDB
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "osha_query_logs")
DYNAMODB_REGION = os.getenv("DYNAMODB_REGION", "us-east-1")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "./logs/app.log")


def validate():
    missing = []
    if not AWS_ACCESS_KEY_ID:
        missing.append("AWS_ACCESS_KEY_ID")
    if not AWS_SECRET_ACCESS_KEY:
        missing.append("AWS_SECRET_ACCESS_KEY")
    if not os.path.isdir(DOCS_DIR):
        raise EnvironmentError(f"DOCS_DIR not found: {DOCS_DIR}")
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")