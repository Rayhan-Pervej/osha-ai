import re


CHUNK_SIZE = 3000
CHUNK_OVERLAP = 500
MIN_CHUNK_THRESHOLD = 5000


def chunk_text(text: str) -> list[str]:
    if len(text) <= MIN_CHUNK_THRESHOLD:
        return [text]

    paragraphs = text.split("\n\n")
    if len(paragraphs) == 1:
        paragraphs = text.split("\n")

    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) > CHUNK_SIZE and current:
            chunks.append(current.strip())
            current = current[-CHUNK_OVERLAP:] + "\n" + para
        else:
            current = current + "\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def chunk_cfr_section(item: dict) -> list[dict]:
    content = item.get("content", "").strip()
    if not content:
        return []

    chunks = chunk_text(content)

    docs = []
    for i, chunk in enumerate(chunks):
        docs.append({
            "section_id":   item["section"],
            "chunk_index":  i,
            "total_chunks": len(chunks),
            "source":       item.get("source", ""),
            "title":        item.get("title", ""),
            "path":         item.get("path", ""),
            "local_path":   "",
            "raw_content":  chunk,
        })
    return docs


def chunk_osh_act_section(key: str, text: str) -> list[dict]:
    text = text.strip()
    if not text:
        return []

    section_id = "OSH-Act-" + re.sub(r"[^a-zA-Z0-9]+", "-", key).strip("-")
    chunks = chunk_text(text)

    docs = []
    for i, chunk in enumerate(chunks):
        docs.append({
            "section_id":   section_id,
            "chunk_index":  i,
            "total_chunks": len(chunks),
            "source":       "Occupational Safety and Health Act",
            "title":        key,
            "path":         key,
            "local_path":   "",
            "raw_content":  chunk,
        })
    return docs


def chunk_fom_chapter(filename: str, text: str) -> list[dict]:
    text = text.strip()
    if not text:
        return []

    chapter_name = filename.replace(".txt", "")
    chunks = chunk_text(text)

    docs = []
    for i, chunk in enumerate(chunks):
        docs.append({
            "section_id":   f"FOM-{chapter_name}",
            "chunk_index":  i,
            "total_chunks": len(chunks),
            "source":       "OSHA Field Operations Manual",
            "title":        chapter_name,
            "path":         filename,
            "local_path":   "",
            "raw_content":  chunk,
        })
    return docs
