from src.config import settings
from src.rag.discover import discover
from src.services.logger import log_query

settings.validate()

CLIENT_ID = "test-client"
AGENT_ID  = "test-agent"


def print_results(results: list):
    print(f"\n{'─' * 60}")
    print(f"  Found {len(results)} result(s)")
    print(f"{'─' * 60}")
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['title']}")
        print(f"    Section : {r['section_id']}")
        print(f"    Source  : {r['source']}")
        print(f"    Score   : {r['score']} ({r['relevance']})")
        print(f"    Excerpt : {r['excerpt'][:500]}...")
    print(f"\n{'─' * 60}")


def main():
    print("\n=== OSHA AI Agent (discover test) ===")
    print("Type 'quit' to exit\n")

    while True:
        query = input("Your query: ").strip()
        if query.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break
        if not query:
            continue

        print("\nSearching knowledge base...")
        result = discover(query)

        if not result["results"]:
            print("No results found.\n")
            continue

        if result.get("ambiguous"):
            parts = sorted(result["parts_found"])
            labels = result["parts_labels"]
            print("\nYour query matches multiple regulatory parts. Which applies to your situation?")
            for i, p in enumerate(parts, 1):
                print(f"  {i}. {labels.get(p, p)}")
            choice = input("\nEnter number: ").strip()
            if not choice.isdigit() or not (1 <= int(choice) <= len(parts)):
                print("Invalid choice.\n")
                continue
            part = parts[int(choice) - 1]
            result = discover(query, part_filter=part)
            if not result["results"]:
                print("No results found for that part.\n")
                continue

        print_results(result["results"])

        log_query(
            client_id=CLIENT_ID,
            agent_id=AGENT_ID,
            query=query,
            returned_section_ids=[r["section_id"] for r in result["results"]],
            locked_section_ids=None,
            generation_invoked=False,
        )


if __name__ == "__main__":
    main()
