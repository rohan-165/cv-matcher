"""
search.py

Search your ingested candidates by job requirement.

Examples:
    python3 search.py "Flutter developer with BLE and wearable SDK experience"
    python3 search.py "iOS developer, Swift, 3+ years" --top 5
    python3 search.py "backend developer Python Django" --top 10 --export shortlist.xlsx
    python3 search.py "React Native developer" --min-score 0.5   # stricter cutoff
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
    parser.add_argument("--min-score", type=float, default=embedder.DEFAULT_MIN_SCORE,
                         help=f"Minimum match score (0-1) to be shown at all (default: {embedder.DEFAULT_MIN_SCORE}). "
                              "Raise it for a stricter shortlist, lower it if you're not finding anyone.")
    parser.add_argument("--export", help="Optional path to export shortlist as .xlsx (e.g. shortlist.xlsx)")
    args = parser.parse_args()

    if embedder.candidate_count() == 0:
        print("No candidates ingested yet. Run `python3 ingest.py` first.")
        sys.exit(0)

    results = embedder.query(args.query, top_k=args.top, min_score=args.min_score)

    if not results:
        print(f"\nNo relevant candidates found for: \"{args.query}\" (min score: {args.min_score})")
        print("Try describing the role differently, or lower --min-score to widen the search.")
        sys.exit(0)

    print(f"\nTop {len(results)} match(es) for: \"{args.query}\"\n")

    rows = []
    for i, r in enumerate(results, start=1):
        meta = r["metadata"]
        print(f"{i}. {meta.get('full_name') or '(name not detected)'}  "
              f"— match score: {r['score']}  "
              f"(semantic: {r['semantic_score']}, keyword: {r['keyword_score']})")
        print(f"   Email: {meta.get('email') or '-'}  |  Phone: {meta.get('phone') or '-'}  "
              f"|  Location: {meta.get('location') or '-'}")
        print(f"   Skills: {meta.get('skills') or '-'}")
        print(f"   Source file: {meta.get('source_file')}")
        print()

        rows.append({
            "rank": i,
            "match_score": r["score"],
            "semantic_score": r["semantic_score"],
            "keyword_score": r["keyword_score"],
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