"""
Convert OSHA JSON files to .txt format for Bedrock Knowledge Base ingestion.
Output: data/normalized/ (all files flat in one folder)
"""

import json
import shutil
from pathlib import Path

RAW_DIR = Path("data/raw/osha_documents")
OUT_DIR = Path("data/normalized")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def convert_cfr_json(json_path: Path):
    """
    Handles list-based JSONs (title-29-chapter-17-*.json)
    Each entry has: source, title, section, content, path
    Each entry becomes one .txt file.
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or len(data) == 0:
        print(f"  Skipping {json_path.name} — empty or not a list")
        return

    count = 0
    skipped = 0
    for entry in data:
        content = str(entry.get("content", "")).strip()
        if len(content) < 50:
            skipped += 1
            continue

        source = entry.get("source", "unknown").strip()
        title = entry.get("title", "").strip()
        section = entry.get("section", "").strip()
        path = entry.get("path", "").strip()

        # safe filename from source e.g. "29 CFR 1910.1" -> "29_CFR_1910_1"
        safe_name = source.replace(" ", "_").replace("/", "_").replace(".", "_")
        out_file = OUT_DIR / f"{safe_name}.txt"

        lines = []
        if source:
            lines.append(f"Source: {source}")
        if title:
            lines.append(f"Title: {title}")
        if section:
            lines.append(f"Section: {section}")
        if path:
            lines.append(f"Path: {path}")
        lines.append("")
        lines.append(content)

        out_file.write_text("\n".join(lines), encoding="utf-8")
        count += 1

    print(f"  {json_path.name}: {count} files written, {skipped} empty entries skipped")


def convert_osha_act(json_path: Path):
    """
    Handles osha-act.json which is a dict: { "SEC. X. Title": "content text" }
    All sections go into a single .txt file.
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        print(f"  Skipping {json_path.name} — unexpected format")
        return

    out_file = OUT_DIR / "osha-act.txt"
    lines = ["OSHA ACT (Public Law 91-596)", "=" * 60, ""]

    for section_title, content in data.items():
        content = str(content).strip()
        lines.append(f"{'=' * 60}")
        lines.append(section_title)
        lines.append(f"{'=' * 60}")
        lines.append(content)
        lines.append("")

    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"  {json_path.name}: written as single file -> {out_file}")


def copy_txt_files():
    """Copy existing .txt files from raw/osha_documents into normalized folder."""
    txt_files = list(RAW_DIR.glob("*.txt"))
    for src in txt_files:
        dst = OUT_DIR / src.name
        shutil.copy2(src, dst)
    print(f"  Copied {len(txt_files)} existing .txt files from {RAW_DIR}")


def main():
    # Clean up any old subfolders from previous runs
    for item in OUT_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
            print(f"  Removed old subfolder: {item.name}")

    json_files = list(RAW_DIR.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in {RAW_DIR}")
        return

    print(f"Found {len(json_files)} JSON files in {RAW_DIR}\n")

    for json_path in sorted(json_files):
        print(f"Processing: {json_path.name}")
        if json_path.name == "osha-act.json":
            convert_osha_act(json_path)
        else:
            convert_cfr_json(json_path)

    print(f"\nCopying existing TXT files...")
    copy_txt_files()

    total = len(list(OUT_DIR.glob("*.txt")))
    print(f"\nDone. {total} total .txt files in: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
