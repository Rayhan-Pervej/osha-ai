import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.processors.chunker import chunk_cfr_section, chunk_osh_act_section, chunk_fom_chapter

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "osha_documents")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "chunks.json")


def build():
    all_chunks = []

    text_files = sorted(f for f in os.listdir(DOCS_DIR) if f.endswith(".txt"))
    print(f"Processing {len(text_files)} .txt files...")

    for filename in text_files:
        filepath = os.path.join(DOCS_DIR, filename)
        with open(filepath, encoding="utf-8") as f:
            body = f.read()

        chunks = chunk_fom_chapter(filename, body)
        for chunk in chunks:
            chunk["local_path"] = filepath
        all_chunks.extend(chunks)
        print(f"  {filename} -> {len(chunks)} chunks")

    json_files = sorted(f for f in os.listdir(DOCS_DIR) if f.endswith(".json"))
    print(f"Processing {len(json_files)} .json files...")

    for filename in json_files:
        filepath = os.path.join(DOCS_DIR, filename)
        with open(filepath, encoding="utf-8") as f:
            raw = json.load(f)

        count = 0

        if isinstance(raw, list):
            for item in raw:
                if not item.get("content", "").strip():
                    continue
                chunks = chunk_cfr_section(item)
                all_chunks.extend(chunks)
                count += len(chunks)

        elif isinstance(raw, dict):
            for key, text in raw.items():
                if not isinstance(text, str) or not text.strip():
                    continue
                chunks = chunk_osh_act_section(key, text)
                all_chunks.extend(chunks)
                count += len(chunks)

        print(f"  {filename} -> {count} chunks")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False)

    print(f"\nTotal: {len(all_chunks)} chunks saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    build()
