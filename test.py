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
    print("  3. search_regulations — JSON string (how agent calls it)")
    level = input("Choice (1/2/3): ").strip()

    if level == "1":
        from src.agent.tools.search_regulations import discover
        result = discover(query, part_filter=part)
        print(json.dumps(result, indent=2))

    elif level == "2":
        from src.agent.tools.search_regulations import search_regulations
        result = search_regulations.invoke({"query": query, "part_filter": part})
        parsed = json.loads(result)
        print(json.dumps(parsed, indent=2))

    elif level == "3":
        from src.retrieval.bedrock_kb import retrieve_for_section
        results = retrieve_for_section(query, section=part or "1910", top_k=5)
        print(json.dumps(results, indent=2))
        

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
    parsed = json.loads(result)
    print(f"\nsummary:\n{parsed.get('summary', '')}")
    print(f"\nbullets ({len(parsed.get('bullets', []))}):")
    for b in parsed.get("bullets", []):
        print(f"  {b.get('citations', [])} {b.get('text', '')}")
    print(f"\nwhy:\n{parsed.get('why', '')}")
    print(f"\nconfidence_percent: {parsed.get('confidence_percent')}%")
    print(f"verbatim_percent:   {parsed.get('verbatim_percent')}%")
    print(f"section:            {parsed.get('section')}")


def test_agent():
    import logging
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    from src.agent.graph import graph

    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("osha.agent.debug").setLevel(logging.WARNING)
    logging.getLogger("src").setLevel(logging.WARNING)

    print("\nAgent test — multi-turn conversation.")
    print("Type your message. Watch every node: agent thinking, tool calls, tool outputs.")
    print("Type 'exit' to quit.\n")

    history = []

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() == "exit":
            break
        if not user_input:
            continue

        history.append(HumanMessage(content=user_input))

        print()
        final_state = None
        printed_ids = set()
        for step in graph.stream(
            {"messages": history},
            config={"recursion_limit": 12},
            stream_mode="values",
        ):
            final_state = step
            msgs = step.get("messages", [])
            if not msgs:
                continue
            last = msgs[-1]

            msg_id = id(last)
            if msg_id in printed_ids:
                continue
            printed_ids.add(msg_id)

            if isinstance(last, AIMessage) and last.tool_calls:
                print(f"[agent] calling tools:")
                for tc in last.tool_calls:
                    print(f"  -> {tc['name']}({json.dumps(tc.get('args', {}))})")
            elif isinstance(last, ToolMessage):
                print(f"\n[tool: {last.name}] output:")
                print(last.content)
            elif isinstance(last, AIMessage) and not last.tool_calls:
                print(f"\n[agent] response:")
                print(last.content)
            print()

        structured = final_state.get("structured_output") if final_state else None
        if structured and structured.get("type") == "generate_result":
            print("--- Scores ---")
            print(f"Section:    {structured.get('section')}")
            print(f"Confidence: {structured.get('confidence_percent')}%")
            print(f"Verbatim:   {structured.get('verbatim_percent')}%")
            print(f"Bullets:    {len(structured.get('bullets', []))}")
            print()

        if final_state:
            history = list(final_state["messages"])


def main():
    print("What do you want to test?")
    print("  1. search")
    print("  2. generate")
    print("  3. agent")
    choice = input("Choice (1/2/3): ").strip()

    if choice == "1":
        test_search()
    elif choice == "2":
        test_generate()
    elif choice == "3":
        test_agent()
    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
