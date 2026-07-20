"""CLI: python main.py "Compare X and Y on <criteria> for a <N>-person team"."""

import sys

from src.agent import run_agent


def print_trace(result):
    """Print the accumulated per-node trace for debugging and auditing."""
    print("\n" + "-" * 72 + "\nTRACE\n" + "-" * 72)
    trace = result.get("trace", [])
    if not trace:
        print("  (no trace entries)")
        return
    for index, entry in enumerate(trace, start=1):
        print(f"  {index:02d}. {entry}")


def main():
    if len(sys.argv) < 2:
        print('Usage: python main.py "Compare X and Y on <criteria> for a <N>-person team"')
        sys.exit(1)

    result = run_agent(" ".join(sys.argv[1:]))
    final = result["final"]

    print("\n" + "=" * 72)
    if final.get("type") == "clarify":
        print("CLARIFYING QUESTION\n" + "=" * 72)
        print(final["question"])
        print_trace(result)
        return

    print("ANSWER\n" + "=" * 72)
    print(result["answer"])

    print("\n" + "-" * 72 + "\nSTRUCTURED CELLS\n" + "-" * 72)
    for c in final["cells"]:
        cite = f" [{c['citation_id']}]" if c["citation_id"] else ""
        print(f"  {c['product']} / {c['criterion']}: {c['label']}{cite}")

    if final.get("cost", {}).get("lines"):
        print("\n" + "-" * 72 + "\nCOST\n" + "-" * 72)
        for line in final["cost"]["lines"]:
            print("  " + line)

    if final.get("unverified"):
        print("\n" + "-" * 72 + "\nUNVERIFIED\n" + "-" * 72)
        for u in final["unverified"]:
            print("  " + u)

    print("\n" + "-" * 72 + "\nSOURCES\n" + "-" * 72)
    for s in final["sources"]:
        print("  " + s)

    s = result["stats"]
    print("\n" + "-" * 72)
    print(f"grounding rate: {final['grounding_rate']:.0%}")
    print(f"stats: {s['llm_calls']} llm | {s['tool_calls']} tool | {s['steps']} steps "
          f"| {s['retries']} retries | {s['revisions']} revisions | {s['seconds']}s")
    print_trace(result)


if __name__ == "__main__":
    main()
