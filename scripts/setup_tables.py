import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3
from src.config import settings

db = boto3.client(
    "dynamodb",
    region_name=settings.DYNAMODB_REGION,
    endpoint_url=settings.DYNAMODB_ENDPOINT,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
)

TABLES = [
    {
        "TableName": settings.DYNAMODB_TABLE_CLIENTS,
        "KeySchema": [{"AttributeName": "client_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "client_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.DYNAMODB_TABLE_AGENTS,
        "KeySchema": [{"AttributeName": "agent_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "agent_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.DYNAMODB_TABLE_API_KEYS,
        "KeySchema": [{"AttributeName": "embed_key", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "embed_key", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.DYNAMODB_TABLE_QUERY_LOGS,
        "KeySchema": [{"AttributeName": "query_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "query_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": settings.DYNAMODB_TABLE_SESSIONS,
        "KeySchema": [{"AttributeName": "session_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "session_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
]


def create_tables():
    existing = db.list_tables()["TableNames"]
    for table in TABLES:
        name = table["TableName"]
        if name in existing:
            print(f"  skipped  {name} (already exists)")
        else:
            db.create_table(**table)
            print(f"  created  {name}")


if __name__ == "__main__":
    print("Creating DynamoDB tables...")
    create_tables()
    print("Done.")
