"""
webapp/server.py

A tiny local web server for searching candidates in a browser instead of
the command line. Reuses the exact same embedder.query() and candidate
JSON files as search.py / ingest.py - this is just a UI on top of them.

Run it:
    cd cv-matcher
    source .venv/bin/activate
    python3 webapp/server.py

Then open http://127.0.0.1:8765 in your browser.

Bound to 127.0.0.1 only (not 0.0.0.0) - this stays local to your machine,
same as the rest of the pipeline.
"""

import json
import os
import sys
from datetime import datetime

import pandas as pd
from flask import Flask, jsonify, request, send_file, send_from_directory

WEBAPP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(WEBAPP_DIR)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import embedder  # noqa: E402  (path must be set up first)

CANDIDATES_DIR = os.path.join(PROJECT_ROOT, "data", "candidates")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
HOST = "127.0.0.1"
PORT = 8765

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(WEBAPP_DIR, "index.html")


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    top_k = int(request.args.get("top", 10))
    min_score = float(request.args.get("min_score", embedder.DEFAULT_MIN_SCORE))

    if not query:
        return jsonify({"error": "Type a job requirement to search for."}), 400

    if embedder.candidate_count() == 0:
        return jsonify({
            "query": query, "count": 0, "results": [],
            "message": "No candidates ingested yet. Run ingest.py first.",
        })

    try:
        results = embedder.query(query, top_k=top_k, min_score=min_score)
    except Exception as e:
        return jsonify({"error": f"Search failed: {e}"}), 500

    message = None if results else f"No relevant candidates found (min score: {min_score})."
    return jsonify({"query": query, "count": len(results), "results": results, "message": message})


@app.route("/api/candidate/<candidate_id>")
def api_candidate(candidate_id):
    path = os.path.join(CANDIDATES_DIR, f"{candidate_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Candidate record not found."}), 404
    with open(path) as f:
        return jsonify(json.load(f))


@app.route("/api/export", methods=["POST"])
def api_export():
    body = request.get_json(force=True) or {}
    candidate_ids = body.get("candidate_ids", [])

    rows = []
    for cid in candidate_ids:
        path = os.path.join(CANDIDATES_DIR, f"{cid}.json")
        if not os.path.exists(path):
            continue
        record = json.load(open(path))
        p = record.get("parsed", {})
        rows.append({
            "full_name": p.get("full_name"),
            "email": p.get("email"),
            "phone": p.get("phone"),
            "location": p.get("location"),
            "total_experience_years": p.get("total_experience_years"),
            "skills": ", ".join(p.get("skills") or []),
            "source_file": record.get("source_file"),
            "candidate_id": cid,
        })

    if not rows:
        return jsonify({"error": "No valid candidates selected for export."}), 400

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"shortlist_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    out_path = os.path.join(OUTPUT_DIR, filename)
    pd.DataFrame(rows).to_excel(out_path, index=False)

    return send_file(out_path, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    print(f"Candidate search running at http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)