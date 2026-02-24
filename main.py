from src.config import settings
from src.exceptions.errors import OshaNoResultsError
from src.rag.discover import discover
from src.rag.generate import generate
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


def print_answer(result: dict):
    a = result["answer"]
    print(f"\n{'═' * 60}")
    print("  GENERATED ANSWER")
    print(f"{'═' * 60}")
    print(a.get("answer", ""))
    print(f"\n  Confidence : {a.get('confidence_score', '?')} — {a.get('confidence', '')}")
    print(f"  Verbatim   : {a.get('verbatim_score', '?')}")
    if a.get("verbatim_quotes"):
        print(f"  Quotes     : {a['verbatim_quotes']}")
    print(f"\n  Locked sections: {', '.join(result['locked_section_ids'])}")
    print(f"{'═' * 60}\n")



def main():
    print("\n=== OSHA AI Agent ===")
    print("Type 'quit' to exit\n")

    while True:
        query = input("Your query: ").strip()
        if query.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break
        if not query:
            continue

        print("\nSearching knowledge base...")
        try:
            result = discover(query)
        except OshaNoResultsError:
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
            try:
                result = discover(query, part_filter=part)
            except OshaNoResultsError:
                print("No results found for that part.\n")
                continue

        print_results(result["results"])

        # lock sections for generation
        print("Enter section number(s) to lock for a detailed answer (e.g. 1 or 1,2,3)")
        print("Press Enter to skip generation.")
        lock_input = input("Lock: ").strip()

        locked_sections = []
        generation_invoked = False

        if lock_input:
            indices = []
            for part in lock_input.split(","):
                part = part.strip()
                if part.isdigit() and 1 <= int(part) <= len(result["results"]):
                    indices.append(int(part) - 1)

            if not indices:
                print("Invalid selection. Skipping generation.\n")
            else:
                locked_sections = [result["results"][i] for i in indices]
                locked_ids = [s["section_id"] for s in locked_sections]
                print(f"\nLocked: {', '.join(locked_ids)}")
                print("Generating answer...\n")

                try:
                    gen_result = generate(query, locked_sections)
                    print_answer(gen_result)
                    generation_invoked = True
                except Exception as e:
                    print(f"Generation failed: {e}\n")

        log_query(
            client_id=CLIENT_ID,
            agent_id=AGENT_ID,
            query=query,
            returned_section_ids=[r["section_id"] for r in result["results"]],
            locked_section_ids=[s["section_id"] for s in locked_sections] if locked_sections else None,
            generation_invoked=generation_invoked,
        )


if __name__ == "__main__":
    main()
