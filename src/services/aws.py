import boto3
from src.config import settings

_dynamodb_client = None
_bedrock_client = None


def get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return _bedrock_client


def get_dynamodb_client():
    global _dynamodb_client
    if _dynamodb_client is None:
        kwargs = {
            "region_name": settings.DYNAMODB_REGION,
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
        }
        if settings.DYNAMODB_ENDPOINT:
            kwargs["endpoint_url"] = settings.DYNAMODB_ENDPOINT
        _dynamodb_client = boto3.client("dynamodb", **kwargs)
    return _dynamodb_client
