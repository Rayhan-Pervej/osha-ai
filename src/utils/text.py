_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "not", "nor", "so", "yet",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "up",
    "about", "into", "through", "during", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "may", "might", "must", "can",
    "could", "that", "this", "these", "those", "it", "its", "they",
    "them", "their", "we", "our", "you", "your", "i", "my", "what",
    "how", "when", "where", "which", "who", "why", "any", "all", "each",
    "every", "some", "more", "most", "also", "as", "if",
})


def _stem(word: str) -> str:
    """Iterative suffix stemmer for English OSHA regulatory text.

    Applied to both index tokens and query tokens so they match consistently.
    Iterates until no more suffixes are stripped, ensuring "inspections" and
    "inspection" both reduce to the same root.
    Does NOT stem short words (len <= 4) to protect CFR numbers and acronyms.
    """
    if len(word) <= 4:
        return word

    prev = None
    while word != prev:
        prev = word
        w = word

        # longest suffixes first to avoid partial stripping

        if w.endswith("ization") and len(w) > 9:
            word = w[:-7] + "ize"; continue
        if w.endswith("isation") and len(w) > 9:
            word = w[:-7] + "ize"; continue

        if w.endswith("ations") and len(w) > 8:
            word = w[:-6]; continue          # "regulations" → "regul" (via -ations)
        if w.endswith("ation") and len(w) > 7:
            word = w[:-5]; continue          # "regulation" → "regul"

        if w.endswith("tions") and len(w) > 7:
            word = w[:-5] + "t"; continue    # "inspections" → "inspect"
        if w.endswith("tion") and len(w) > 6:
            word = w[:-3]; continue          # "inspection" → "inspect"

        if w.endswith("sions") and len(w) > 7:
            word = w[:-5] + "s"; continue
        if w.endswith("sion") and len(w) > 6:
            word = w[:-3]; continue

        if w.endswith("ments") and len(w) > 7:
            word = w[:-5]; continue
        if w.endswith("ment") and len(w) > 6:
            word = w[:-4]; continue

        if w.endswith("nesses") and len(w) > 8:
            word = w[:-6]; continue
        if w.endswith("ness") and len(w) > 6:
            word = w[:-4]; continue

        if w.endswith("ities") and len(w) > 7:
            word = w[:-5]; continue
        if w.endswith("ity") and len(w) > 5:
            word = w[:-3]; continue

        if w.endswith("ies") and len(w) > 5:
            word = w[:-3] + "y"; continue
        if w.endswith("ied") and len(w) > 5:
            word = w[:-3] + "y"; continue

        if w.endswith("ing") and len(w) > 6:
            root = w[:-3]
            if len(root) >= 3 and root[-1] == root[-2]:  # "running" → "run"
                word = root[:-1]; continue
            word = root; continue          # "providing" → "provid", "scaffolding" → "scaffold"

        if w.endswith("ed") and len(w) > 5:
            root = w[:-2]
            if len(root) >= 3 and root[-1] == root[-2]:  # "planned" → "plan"
                word = root[:-1]; continue
            word = root; continue          # "required" → "requir", "provided" → "provid"

        if w.endswith("ers") and len(w) > 5:
            word = w[:-3]; continue
        if w.endswith("er") and len(w) > 5:
            word = w[:-2]; continue

        if w.endswith("ly") and len(w) > 5:
            word = w[:-2]; continue

        if w.endswith("ious") and len(w) > 6:
            word = w[:-4]; continue
        if w.endswith("ous") and len(w) > 5:
            word = w[:-3]; continue

        if w.endswith("ive") and len(w) > 5:
            word = w[:-3]; continue

        if w.endswith("ize") and len(w) > 5:
            word = w[:-3]; continue
        if w.endswith("ise") and len(w) > 5:
            word = w[:-3]; continue

        if w.endswith("ful") and len(w) > 5:
            word = w[:-3]; continue

        if w.endswith("al") and len(w) > 5:
            word = w[:-2]; continue

        # -es: only strip -s (keep the e) to avoid "gloves"→"glov"
        # exception: -ches/-shes/-xes/-zes strip -es (no silent e)
        if w.endswith("es") and len(w) > 5 and not w.endswith("ss"):
            if w.endswith(("ches", "shes", "xes", "zes")):
                word = w[:-2]; continue   # "processes" → leave as "process" via -s below
            word = w[:-1]; continue       # "gloves" → "glove", "employees" → "employee"

        if w.endswith("s") and len(w) > 4 and not w.endswith("ss"):
            word = w[:-1]; continue

        # strip trailing silent -e to unify "require"→"requir" with "required"→"requir"
        if w.endswith("e") and len(w) > 4:
            word = w[:-1]; continue

        # no rule fired — stop
        break

    return word
