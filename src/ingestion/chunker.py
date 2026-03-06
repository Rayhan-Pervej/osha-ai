from pathlib import Path
from dataclasses import dataclass, asdict

PARENT_CHUNK_SIZE = 1500
CHILD_CHUNK_SIZE = 300
CHUNK_OVERLAP = 80


@dataclass
class Chunk:
    chunk_id: str
    parent_id: str
    source_file: str
    source: str
    title: str
    section: str
    path: str
    chunk_type: str
    text: str
    char_start: int
    char_end: int

    def to_dict(self):
        return asdict(self)
    

def parse_metadata(file_path: Path) -> tuple[dict, str]:
    """
    Reads a .txt file and splits it into:
      - metadata dict  (source, title, section, path)
      - body string    (the actual document content)

    Returns:
        (metadata, body)
    """

    text = file_path.read_text(encoding='utf-8')
    lines = text.splitlines()

    metadata = {
        'source': '',
        'title': '',
        'section': '',
        'path': ''
    }

    known_keys = {"Source", "Title", "Section", "Path"}
    body_start = 0

    for i, line in enumerate(lines):

        if line.strip() == '':
            body_start = i + 1
            break

        if ":" in line:
            key, _, value = line.partition(":")
            if key.strip() in known_keys:
                metadata[key.strip().lower()] = value.strip()

    body = "\n".join(lines[body_start:])

    return metadata, body

def split_into_parents(body: str) -> list[tuple[int, int]]:
    """
    Splits the body text into parent-sized spans.
    Parents are split on double newlines, but if a span is too big it will be split on single newlines.

    Returns a list of (start, end) character positions relative to the full body.
    """

    spans = []
    start = 0
    length = len(body)

    while start < length:
        end = min(start + PARENT_CHUNK_SIZE, length)

        if end < length:
            search_from = start + int(PARENT_CHUNK_SIZE * 0.8)
            para_break = body.rfind("\n\n", search_from, end)
            if para_break != -1:
                end = para_break + 2
            else:
                sentence_end = -1
                for punct in ('.', '!', '?'):
                    pos = body.rfind(punct, search_from, end)
                    if pos > sentence_end:
                        sentence_end = pos
                if sentence_end != -1:
                    end = sentence_end + 1

        spans.append((start, end))
        start = end
    
    return spans

def split_into_children(body: str, parent_start: int, parent_end: int) -> list[tuple[int, int]]:
    """
    Splits one parent span into child-sized spans.
    Children overlap by CHUNK_OVERLAP chars so context isn't lost at boundaries.

    Returns a list of (start, end) character positions relative to the full body.
    """

    spans = []
    start = parent_start

    while start < parent_end:
        end = min(start + CHILD_CHUNK_SIZE, parent_end)
        

        if end < parent_end:
            search_from = start + int(CHILD_CHUNK_SIZE * 0.7)
            if search_from < end:
                sentence_end = -1
                for punct in ('.', '!', '?'):
                    pos = body.rfind(punct, search_from, end)
                    if pos > sentence_end:
                        sentence_end = pos
                if sentence_end != -1:
                    end = sentence_end + 1

        spans.append((start, end))

        next_start = end - CHUNK_OVERLAP
        if next_start <= start:
            next_start = end  # skip overlap on tiny chunks
        start = next_start

    return spans




def chunk_file(file_path: Path) -> list[Chunk]:
    """
    Main entry point. Takes one .txt file and returns a flat list of Chunk objects.
    Both parent and child chunks are returned together.
    Caller can filter by chunk_type == "parent" or "child".
    """


    metadata, body = parse_metadata(file_path)

    if len(body.strip()) < 50:
        return []
    
    base_id = file_path.stem

    chunks =[]

    parent_spans = split_into_parents(body)


    for p_idx, (p_start, p_end) in enumerate(parent_spans):
        parent_text = body[p_start:p_end].strip()
        parent_id   = f"{base_id}__p{p_idx}"

        parent_chunk = Chunk(
            chunk_id=parent_id,
            parent_id   = parent_id,   # parent points to itself
            source_file = file_path.name,
            source      = metadata["source"],
            title       = metadata["title"],
            section     = metadata["section"],
            path        = metadata["path"],
            chunk_type  = "parent",
            text        = parent_text,
            char_start  = p_start,
            char_end    = p_end,
        )

        chunks.append(parent_chunk)

        child_spans = split_into_children(body, p_start, p_end)


        for c_idx, (c_start, c_end) in enumerate(child_spans):
            child_text = body[c_start:c_end].strip()

            if len(child_text) < 20:
                continue

            child_chunk = Chunk(
                chunk_id    = f"{parent_id}__c{c_idx}",
                parent_id   = parent_id,   # child points to its parent
                source_file = file_path.name,
                source      = metadata["source"],
                title       = metadata["title"],
                section     = metadata["section"],
                path        = metadata["path"],
                chunk_type  = "child",
                text        = child_text,
                char_start  = c_start,
                char_end    = c_end,
            )
            chunks.append(child_chunk)

    return chunks


def chunk_all_files(normalized_dir: Path, output_path: Path) -> list[Chunk]:
    """
    Processes all .txt files in normalized_dir.
    Saves all chunks to output_path as JSON.
    Returns the full list of Chunk objects.
    """
    import json

    text_files = sorted(normalized_dir.glob("*.txt"))

    if not text_files:
        print(f"No .txt files found in {normalized_dir}")
        return []
    
    all_chunks = []
    total_files = len(text_files)

    for i, file_path in enumerate(text_files, 1):
        chunks = chunk_file(file_path)
        all_chunks.extend(chunks)
        print(f"  [{i}/{total_files}] {file_path.name} -> {len(chunks)} chunks")


    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump([c.to_dict() for c in all_chunks], f, indent=2)

    parents = sum(1 for c in all_chunks if c.chunk_type == "parent")
    children = sum(1 for c in all_chunks if c.chunk_type == "child")

    print(f"\nDone.")
    print(f"  Total files   : {total_files}")
    print(f"  Parent chunks : {parents}")
    print(f"  Child chunks  : {children}")
    print(f"  Saved to      : {output_path}")



if __name__ == "__main__":
    normalized_dir = Path("data/normalized")
    output_path    = Path("data/processed/chunks.json")
    chunk_all_files(normalized_dir, output_path)