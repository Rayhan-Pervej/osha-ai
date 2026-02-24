import json
import logging
import os
import re

from rank_bm25 import BM25Okapi

from src.config import settings
from src.exceptions.errors import OshaIndexError, OshaDocumentNotFoundError
from src.utils.text import _STOP_WORDS

logger = logging.getLogger(__name__)

_index: BM25Okapi | None = None
_docs: list[dict] | None = None


def _tokenise(text: str, strip_stops: bool = False) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+(?:\.[0-9]+)*", text.lower())
    if strip_stops:
        tokens = [t for t in tokens if t not in _STOP_WORDS]
    return tokens


def _load_index() -> tuple[BM25Okapi, list[dict]]:
    docs_dir = settings.DOCS_DIR
    docs = []
    tokenised = []

    text_files = sorted(f for f in os.listdir(docs_dir) if f.endswith(".txt"))
    logger.info(f"BM25: loading {len(text_files)} .txt files")

    for filename in text_files:
        filepath = os.path.join(docs_dir, filename)
        with open(filepath, encoding="utf-8") as f:
            body = f.read()

        section_id = filename.replace(".txt", "")
        docs.append({
            "section_id":  section_id,
            "source":      filename,
            "title":       section_id,
            "path":        filepath,
            "local_path":  filepath,
            "raw_content": body,
        })
        tokenised.append(_tokenise(body))

    json_files = sorted(f for f in os.listdir(docs_dir) if f.endswith(".json"))
    logger.info(f"BM25: loading {len(json_files)} .json files")

    for filename in json_files:
        filepath = os.path.join(docs_dir, filename)
        with open(filepath, encoding="utf-8") as f:
            raw = json.load(f)

        if isinstance(raw, list):
            for item in raw:
                content = item.get("content", "").strip()
                if not content:
                    continue
                section_id = item.get("section", "")
                title = item.get("title", "")
                docs.append({
                    "section_id":  section_id,
                    "source":      item.get("source", filename),
                    "title":       title,
                    "path":        item.get("path", ""),
                    "local_path":  "",
                    "raw_content": content,
                })
                # prefix built on-the-fly for BM25 boost, never stored
                tokenised.append(_tokenise(f"{section_id} {title} {content}"))

        elif isinstance(raw, dict):
            for section_name, text in raw.items():
                if not isinstance(text, str) or not text.strip():
                    continue
                section_id = "OSH-Act-" + re.sub(r"[^a-zA-Z0-9]+", "-", section_name).strip("-")
                docs.append({
                    "section_id":  section_id,
                    "source":      "Occupational Safety and Health Act",
                    "title":       section_name,
                    "path":        section_name,
                    "local_path":  "",
                    "raw_content": text,
                })
                tokenised.append(_tokenise(
                    f"{section_id} {section_name} Occupational Safety and Health Act OSH Act {text}"
                ))

    if not docs:
        raise OshaIndexError(f"No documents found in {docs_dir}.")

    index = BM25Okapi(tokenised)
    logger.info(f"BM25: index ready — {len(docs)} documents")
    return index, docs


def ensure_index():
    global _index, _docs
    if _index is None:
        _index, _docs = _load_index()


def get_index() -> tuple[BM25Okapi, list[dict]]:
    ensure_index()
    return _index, _docs


def get_raw_content(section_id: str) -> str:
    ensure_index()
    for doc in _docs:
        if doc["section_id"] == section_id:
            return doc["raw_content"]
    raise OshaDocumentNotFoundError(f"Section not found in index: {section_id!r}")
