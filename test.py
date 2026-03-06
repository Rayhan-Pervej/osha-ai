import json

def test_search():
    query = input("Query: ").strip()
    if not query:
        print("No query entered.")
        return

    part = input("Part filter (e.g. 1910 / 1926) or press Enter to skip: ").strip() or None

    print("\nChoose test level:")
    print("  1. discover()        — raw Python dict")
    print("  2. search_regulations — JSON string (how agent calls it)")
    level = input("Choice (1/2): ").strip()

    if level == "1":
        from src.agent.tools.search_regulations import discover
        result = discover(query, part_filter=part)
        print(json.dumps(result, indent=2))

    elif level == "2":
        from src.agent.tools.search_regulations import search_regulations
        result = search_regulations.invoke({"query": query, "part_filter": part})
        parsed = json.loads(result)
        print(json.dumps(parsed, indent=2))

    else:
        print("Invalid choice.")


GENERATE_TEST_CASES = [
    {
        "section": "1904.39",
        "query": "Within how many hours must a fatality be reported to OSHA, and what reporting methods are allowed?",
    },
        {
        "section": "1904.39",
        "query": "What are the reporting deadlines and methods for fatalities, hospitalizations, amputations, and loss of an eye?",
    },
    {
        "section": "1904.1",
        "query": "Are employers with 10 or fewer employees required to keep OSHA injury and illness records?",
    },
    {
        "section": "1903.4",
        "query": "What happens when an employer refuses to allow an OSHA compliance officer to enter the workplace?",
    },
]


def test_generate():
    print("\nGenerate test cases:")
    for i, tc in enumerate(GENERATE_TEST_CASES, 1):
        print(f"  {i}. [{tc['section']}] {tc['query']}")
    print(f"  {len(GENERATE_TEST_CASES) + 1}. Custom section + query")

    choice = input(f"Choice (1-{len(GENERATE_TEST_CASES) + 1}): ").strip()

    try:
        idx = int(choice) - 1
    except ValueError:
        print("Invalid choice.")
        return

    if 0 <= idx < len(GENERATE_TEST_CASES):
        tc = GENERATE_TEST_CASES[idx]
        section = tc["section"]
        query = tc["query"]
    elif idx == len(GENERATE_TEST_CASES):
        section = input("Section (e.g. 1904.39): ").strip()
        query = input("Query: ").strip()
        if not section or not query:
            print("Section and query are required.")
            return
    else:
        print("Invalid choice.")
        return

    print(f"\nSection: {section}")
    print(f"Query:   {query}")
    print("-" * 60)

    from src.agent.tools.generate_answer import generate_answer
    result = generate_answer.invoke({"section": section, "query": query})
    print(result)


def main():
    print("What do you want to test?")
    print("  1. search")
    print("  2. generate")
    print("  3. agent     (coming soon)")
    choice = input("Choice (1/2/3): ").strip()

    if choice == "1":
        test_search()
    elif choice == "2":
        test_generate()
    elif choice == "3":
        print("Not implemented yet.")
    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
