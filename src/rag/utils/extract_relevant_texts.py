import re
from src.rag.utils.text import _STOP_WORDS


def extract_relevant_window(text: str, query: str, max_chars: int = 500) -> str:
    """Find where query terms cluster most densely and return a window of text around that spot."""
    query_terms = [
        t for t in re.findall(r"[a-z0-9]+", query.lower())
        if len(t) > 2 and t not in _STOP_WORDS
    ]

    if not query_terms:
        return text[:max_chars]

    text_lower = text.lower()
    hit_positions = []
    for term in query_terms:
        pos = 0
        while True:
            idx = text_lower.find(term, pos)
            if idx == -1:
                break
            hit_positions.append(idx)
            pos = idx + 1

    if not hit_positions:
        return text[:max_chars]

    half = max_chars // 2
    best_pos = hit_positions[0]
    best_score = 0
    for center in hit_positions:
        score = sum(1 for p in hit_positions if abs(p - center) <= half)
        if score > best_score:
            best_score = score
            best_pos = center

    start = max(0, best_pos - half)
    end = min(len(text), start + max_chars)
    start = max(0, end - max_chars)

    para_start = text.rfind("\n\n", 0, start)
    if para_start != -1 and start - para_start < 300:
        start = para_start + 2

    para_end = text.find("\n\n", end)
    if para_end != -1 and para_end - end < 300:
        end = para_end

    window = text[start:end].strip()
    prefix = "[...extract...]\n" if start > 0 else ""
    suffix = "\n[...extract...]" if end < len(text) else ""
    return prefix + window + suffix