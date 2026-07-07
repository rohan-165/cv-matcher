"""
search.py

Search your ingested candidates by job requirement.

Examples:
    python3 search.py "Flutter developer with BLE and wearable SDK experience"
    python3 search.py "iOS developer, Swift, 3+ years" --top 5
    python3 search.py "backend developer Python Django" --top 10 --export shortlist.xlsx
"""

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import embedder


def main():
    parser = argparse.ArgumentParser(description="Search candidates by job requirement.")
    parser.add_argument("query", help="Job requirement / description to match candidates against")
    parser.add_argument("--top", type=int, default=10, help="Number of candidates to return (default: 10)")
    parser.add_argument("--export", help="Optional path to export shortlist as .xlsx (e.g. shortlist.xlsx)")
    args = parser.parse_args()

    results = embedder.query(args.query, top_k=args.top)

    if not results:
        print("No candidates found. Have you run ingest.py yet?")
        sys.exit(0)

    print(f"\nTop {len(results)} match(es) for: \"{args.query}\"\n")

    rows = []
    for i, r in enumerate(results, start=1):
        meta = r["metadata"]
        print(f"{i}. {meta.get('full_name') or '(name not detected)'}  "
              f"— match score: {r['score']}")
        print(f"   Email: {meta.get('email') or '-'}  |  Phone: {meta.get('phone') or '-'}  "
              f"|  Location: {meta.get('location') or '-'}")
        print(f"   Skills: {meta.get('skills') or '-'}")
        print(f"   Source file: {meta.get('source_file')}")
        print()

        rows.append({
            "rank": i,
            "match_score": r["score"],
            "full_name": meta.get("full_name"),
            "email": meta.get("email"),
            "phone": meta.get("phone"),
            "location": meta.get("location"),
            "skills": meta.get("skills"),
            "source_file": meta.get("source_file"),
            "candidate_id": r["candidate_id"],
        })

    if args.export:
        df = pd.DataFrame(rows)
        out_path = args.export if os.path.isabs(args.export) or os.sep in args.export else os.path.join("output", args.export)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        df.to_excel(out_path, index=False)
        print(f"Shortlist exported to: {out_path}")


if __name__ == "__main__":
    main()
