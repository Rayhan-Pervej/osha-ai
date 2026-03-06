import json
import boto3
import src.config.settings as settings

MODEL_ID   = settings.BEDROCK_EMBEDDING_MODEL_ID
DIMENSIONS = settings.BEDROCK_EMBEDDING_DIMENSIONS

_client = None


def _get_client():
    """Lazy-init Bedrock client — created once, reused."""
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return _client


def embed(text: str) -> list[float]:
    """
    Embed a single text string using Titan.
    Returns a list of floats (the vector).
    """
    client = _get_client()

    body = json.dumps({
        "inputText": text,
        "dimensions": DIMENSIONS,
        "normalize": True,   # normalize to unit length — required for cosine similarity
    })

    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    result = json.loads(response["body"].read())
    return result["embedding"]


# def embed_batch(texts: list[str]) -> list[list[float]]:
#     """
#     Embed a list of texts one by one.
#     """
#     return [embed(text) for text in texts]