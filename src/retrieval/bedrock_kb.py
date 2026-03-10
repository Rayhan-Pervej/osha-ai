import boto3
import logging
from src.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agent-runtime", region_name=settings.AWS_REGION)
    return _client


def retrieve(query: str, top_k: int = 10) -> list[dict]:
    """
    Query Bedrock Knowledge Base with hybrid search.
    Returns list of dicts: text, score, source, location.
    """
    response = _get_client().retrieve(
        knowledgeBaseId=settings.BEDROCK_KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": top_k,
                "overrideSearchType": "HYBRID"
                }
        },
    )

    results = []
    for r in response.get("retrievalResults", []):
       
        results.append({
       
        "text":     r["content"]["text"],
        "score":    round(r.get("score", 0.0), 4),
        "source":   r.get("location", {}).get("s3Location", {}).get("uri", ""),
    
        })

    logger.debug("[KB] query=%r top_k=%d returned=%d", query, top_k, len(results))
    return results


def _section_to_s3_key(section: str) -> str:
    """
    Convert a display section ID back to the S3 filename fragment.
    e.g. "1926.451"                          -> "29_CFR_1926_451"
         "Chapter 6 Penalties and Debt Collection" -> "Chapter 6 Penalties and Debt Collection"
         "osha-act"                           -> "osha-act"
    """
    import re
    if re.match(r"^\d{4}", section):
        parts = section.replace(".", "_").replace("-", "_")
        return f"29_CFR_{parts}"
    return section



def retrieve_for_section(query: str, section: str, top_k: int = 10) -> list[dict]:
    """
    Query KB filtered to a specific section using Bedrock's source URI filter.
    The KB chunks already contain the citation context — no local file needed.
    Falls back to client-side filtering if the metadata filter fails.
    """
    s3_key = _section_to_s3_key(section)

    try:
        response = _get_client().retrieve(
            knowledgeBaseId=settings.BEDROCK_KB_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": top_k,
                    "overrideSearchType": "HYBRID",
                    "filter": {
                        "stringContains": {
                            "key":   "x-amz-bedrock-kb-source-uri",
                            "value": s3_key,
                        }
                    },
                }
            },
        )
        results = []
        for r in response.get("retrievalResults", []):
            s3_uri = r.get("location", {}).get("s3Location", {}).get("uri", "")
            results.append({
                "text":   r["content"]["text"],
                "score":  round(r.get("score", 0.0), 4),
                "source": s3_uri,
            })
        if results:
            logger.debug("[KB] section=%r native filter matched=%d", section, len(results))
            return results
    except Exception as e:
        logger.warning("[KB] native filter failed for section=%r: %s", section, e)

    # Fallback: client-side filter from broader retrieve
    all_hits = retrieve(query, top_k=top_k * 2)
    filtered = [h for h in all_hits if s3_key in h.get("source", "")]
    if filtered:
        logger.debug("[KB] section=%r client-filter matched=%d", section, len(filtered))
        return filtered[:top_k]

    logger.warning("[KB] section=%r no matching docs, returning top unfiltered", section)
    return all_hits[:top_k]









# retrievalConfiguration={
#     "vectorSearchConfiguration": {
#         "numberOfResults": top_k,           # 1-100, how many chunks to return
#         "overrideSearchType": "HYBRID",     # "HYBRID" or "SEMANTIC"
#         "filter": {                         # metadata filter (optional)
#             "stringContains": {
#                 "key": "x-amz-bedrock-kb-source-uri",
#                 "value": s3_key,
#             }
#         },
#         "rerankingConfiguration": {         # reranking (optional, if KB configured)
#             "bedrockRerankingConfiguration": {
#                 "numberOfRerankedResults": top_k,
#                 "modelConfiguration": {
#                     "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/..."
#                 }
#             },
#             "type": "BEDROCK_RERANKING_MODEL"
#         }
#     }
# }






# {
#   "retrievalResults": [
#     {
#       "content": { "text": "chunk text..." },
#       "location": {
#         "type": "S3",
#         "s3Location": { "uri": "s3://bucket/normalized/29_CFR_1926_451.txt" }
#       },
#       "score": 0.85,
#       "metadata": {
#         "x-amz-bedrock-kb-source-uri": "s3://bucket/normalized/29_CFR_1926_451.txt",
#         "x-amz-bedrock-kb-chunk-id": "...",
#         "x-amz-bedrock-kb-data-source-id": "..."
#       }
#     }
#   ],
#   "nextToken": "...",
#   "ResponseMetadata": { ... }
# }
