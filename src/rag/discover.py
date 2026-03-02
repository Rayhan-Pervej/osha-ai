import logging
import re

from src.config import settings
from src.exceptions.errors import OshaNoResultsError
from src.retrieval.bm25 import get_index, _tokenise
from src.utils.extract_relevant_texts import extract_relevant_window

logger = logging.getLogger(__name__)

REGULATORY_PARTS = {
    "1902": "29 CFR Part 1902 (State Plans — Approval and Certification)",
    "1903": "29 CFR Part 1903 (OSHA Inspections and Citations)",
    "1904": "29 CFR Part 1904 (Injury and Illness Recording and Reporting)",
    "1905": "29 CFR Part 1905 (Variances from Standards)",
    "1908": "29 CFR Part 1908 (Consultation Agreements)",
    "1910": "29 CFR Part 1910 (General Industry Standards)",
    "1911": "29 CFR Part 1911 (Rules of Procedure for Rulemaking)",
    "1912": "29 CFR Part 1912 (Advisory Committees on Standards)",
    "1913": "29 CFR Part 1913 (OSHA Records and Reports)",
    "1915": "29 CFR Part 1915 (Shipyard Employment)",
    "1917": "29 CFR Part 1917 (Marine Terminals)",
    "1918": "29 CFR Part 1918 (Longshoring)",
    "1919": "29 CFR Part 1919 (Gear Certification)",
    "1920": "29 CFR Part 1920 (Procedure for Variations)",
    "1921": "29 CFR Part 1921 (Rules of Practice — Variances)",
    "1922": "29 CFR Part 1922 (Investigational Hearings)",
    "1924": "29 CFR Part 1924 (Safety Standards — Federal Service Contracts)",
    "1925": "29 CFR Part 1925 (Safety Standards — Federal Supply Contracts)",
    "1926": "29 CFR Part 1926 (Construction Standards)",
    "1928": "29 CFR Part 1928 (Agriculture)",
    "1949": "29 CFR Part 1949 (Office of Training and Education)",
    "1952": "29 CFR Part 1952 (Approved State Plans — Individual States)",
    "1953": "29 CFR Part 1953 (Changes to State Plans)",
    "1954": "29 CFR Part 1954 (Monitoring State Plans)",
    "1955": "29 CFR Part 1955 (Revocation of State Plan Approval)",
    "1956": "29 CFR Part 1956 (State Plans — Public Employees)",
    "1960": "29 CFR Part 1960 (Federal Agency Safety and Health Programs)",
    "1975": "29 CFR Part 1975 (Coverage of Employers)",
    "1977": "29 CFR Part 1977 (Whistleblower Protection — OSH Act)",
    "1978": "29 CFR Part 1978 (Whistleblower Protection — STAA: Surface Transportation Assistance Act)",
    "1979": "29 CFR Part 1979 (Whistleblower Protection — AIR21: Aviation Investment and Reform Act for the 21st Century)",
    "1980": "29 CFR Part 1980 (Whistleblower Protection — SOX: Sarbanes-Oxley Act)",
    "1981": "29 CFR Part 1981 (Whistleblower Protection — PIPSA: Pipeline Safety Improvement Act)",
    "1982": "29 CFR Part 1982 (Whistleblower Protection — CPSA: Consumer Product Safety Act)",
    "1983": "29 CFR Part 1983 (Whistleblower Protection — FWPCA: Federal Water Pollution Control Act)",
    "1984": "29 CFR Part 1984 (Whistleblower Protection — ACA: Affordable Care Act)",
    "1985": "29 CFR Part 1985 (Whistleblower Protection — NTSSA: National Transit Systems Security Act)",
    "1986": "29 CFR Part 1986 (Whistleblower Protection — SDWA: Safe Drinking Water Act)",
    "1987": "29 CFR Part 1987 (Whistleblower Protection — TSCA: Toxic Substances Control Act)",
    "1988": "29 CFR Part 1988 (Whistleblower Protection — FSMA: Food Safety Modernization Act)",
    "1989": "29 CFR Part 1989 (Whistleblower Protection — Dodd-Frank Wall Street Reform Act)",
    "1990": "29 CFR Part 1990 (Identification of Carcinogens)",
    "1991": "29 CFR Part 1991 (Whistleblower Protection — CGPA: Consumer Financial Protection Act)",
    "1992": "29 CFR Part 1992 (Whistleblower Protection — MAP-21: Moving Ahead for Progress in the 21st Century Act)",
    "FOM":  "OSHA Field Operations Manual",
    "OSH":  "Occupational Safety and Health Act",
}


def _detect_ambiguity(results: list) -> dict | None:
    """Check if top results span 2+ different CFR parts (e.g. 1910 vs 1926)."""
    if len(results) < 2:
        return None

    top_results = [r for r in results if r['score'] >= .60]
    cfr_parts = set()

    for r in top_results:
        part = _get_cfr_part(r["section_id"])
        if part:
            cfr_parts.add(part)

    if len(cfr_parts) < 2:
        return None

    labels = [REGULATORY_PARTS.get(p, f"29 CFR Part {p}") for p in sorted(cfr_parts)]
    return {
        "parts": list(cfr_parts),
        "message": (
            f"Your query matches regulations in multiple regulatory parts: {' and '.join(labels)}. "
            f"Please clarify which applies to your situation before we proceed:\n"
            + "\n".join(f"  • {l}" for l in labels)
        ),
    }


def _get_cfr_part(section_id: str) -> str | None:
    """Extract CFR part prefix from a section_id (e.g. '1910.132' → '1910')."""
    for prefix in REGULATORY_PARTS:
        if section_id.startswith(prefix) and prefix not in ("FOM", "OSH"):
            return prefix
    return None


def _score_label(score: float) -> str:
    if score >= 0.90:
        return "High"
    if score >= 0.75:
        return "Medium"
    return "Low"


def discover(query: str, part_filter: str | None = None) -> dict:
    """Run a BM25 keyword search and return ranked results with optional part filtering."""
    _index, _docs = get_index()

    top_k     = settings.BEDROCK_RETRIEVAL_TOP_K
    min_score = settings.BEDROCK_RETRIEVAL_MIN_SCORE

    query_tokens = _tokenise(query, strip_stops=True)
    raw_scores   = _index.get_scores(query_tokens)

    max_score  = float(max(raw_scores)) if max(raw_scores) > 0 else 1.0
    normalised = [s / max_score for s in raw_scores]

    scored = [
        (normalised[i], _docs[i])
        for i in range(len(_docs))
        if normalised[i] >= min_score
        and (part_filter is None or _get_cfr_part(_docs[i]['section_id']) == part_filter)
    ]

    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:top_k]

    # deduplicate: keep best chunk per section_id
    seen = {}
    for score, doc in scored:
        sid = doc["section_id"]
        if sid not in seen or score > seen[sid][0]:
            seen[sid] = (score, doc)
    scored = list(seen.values())
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        raise OshaNoResultsError(f"No results found for query: {query!r}")

    results = []
    for score, doc in scored:
        score = round(score, 4)
        results.append({
            "section_id": doc["section_id"],
            "source":     doc["source"],
            "title":      doc["title"],
            "path":       doc["path"],
            "local_path": doc["local_path"],
            # excerpt uses raw_content — clean text, no BM25 prefix noise
            "excerpt":    extract_relevant_window(doc["raw_content"], query, max_chars=500),
            "score":      score,
            "relevance":  _score_label(score),
        })

    if part_filter is None:
        ambiguity = _detect_ambiguity(results)
        if ambiguity:
            parts = ambiguity["parts"]
            return {
                "query":         query,
                "ambiguous":     True,
                "parts_found":   parts,
                "parts_labels":  {p: REGULATORY_PARTS.get(p, f"29 CFR Part {p}") for p in parts},
                "clarification": ambiguity["message"],
                "results":       results,
            }

    return {
        "query":         query,
        "ambiguous":     False,
        "total_results": len(results),
        "results":       results,
        "next_step":     "Reply with the section_id(s) you want to lock for a detailed compliance answer.",
    }
