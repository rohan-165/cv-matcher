"""
ingest.py

The main pipeline. Drop resumes (PDF, DOCX, or images) into `input/` and run:

    python3 ingest.py

For each new file it will:
  1. Extract raw text (extractors.py)
  2. Ask a local Ollama model to pull out structured fields (llm_parser.py)
  3. Save a JSON record to data/candidates/<candidate_id>.json
  4. Embed the record and upsert it into the local vector store (embedder.py)

Already-processed files are skipped on the next run (tracked by content hash
in data/manifest.json), so you can keep adding new CVs to input/ over time
and just re-run this script - it only processes what's new.

Use --force to re-process everything (e.g. after changing the LLM prompt).
"""

import argparse
import glob
import hashlib
import json
import os
import sys
import time
import traceback
import uuid
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from extractors import extract_text
from llm_parser import parse_resume_fields, DEFAULT_MODEL
from schema import build_candidate_record, build_embedding_text
import embedder


INPUT_DIR = "input"
CANDIDATES_DIR = "data/candidates"
MANIFEST_PATH = "data/manifest.json"
LOG_DIR = "output"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)
    return {}


def save_manifest(manifest: dict):
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)


def process_file(path: str, model: str, ocr_lang: str) -> dict:
    """Runs the full extract -> parse -> embed -> store steps for one file.
    Returns a log row dict. Never raises - all errors are captured in the log."""
    filename = os.path.basename(path)
    ext = os.path.splitext(path)[1].lower()
    start = time.perf_counter()

    try:
        raw_text = extract_text(path, lang=ocr_lang)

        if not raw_text.strip():
            return {
                "file": filename, "status": "empty", "candidate_id": None,
                "message": "No text could be extracted (blank or unreadable file)",
                "duration_sec": round(time.perf_counter() - start, 3),
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }

        parsed_fields = parse_resume_fields(raw_text, model=model)

        candidate_id = str(uuid.uuid4())
        record = build_candidate_record(
            candidate_id=candidate_id,
            source_file=filename,
            file_type=ext.lstrip("."),
            raw_text=raw_text,
            parsed_fields=parsed_fields,
        )

        os.makedirs(CANDIDATES_DIR, exist_ok=True)
        with open(os.path.join(CANDIDATES_DIR, f"{candidate_id}.json"), "w") as f:
            json.dump(record, f, indent=2)

        embedding_text = build_embedding_text(record)
        embedder.upsert_candidate(
            candidate_id=candidate_id,
            embedding_text=embedding_text,
            metadata={
                "full_name": parsed_fields.get("full_name") or "",
                "email": parsed_fields.get("email") or "",
                "phone": parsed_fields.get("phone") or "",
                "location": parsed_fields.get("location") or "",
                "skills": ", ".join(parsed_fields.get("skills") or []),
                "source_file": filename,
            },
        )

        return {
            "file": filename, "status": "success", "candidate_id": candidate_id,
            "message": parsed_fields.get("full_name") or "(name not detected)",
            "duration_sec": round(time.perf_counter() - start, 3),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "file": filename, "status": "error", "candidate_id": None,
            "message": f"{type(e).__name__}: {e}",
            "duration_sec": round(time.perf_counter() - start, 3),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }


def main():
    parser = argparse.ArgumentParser(description="Ingest resumes into JSON records + vector search index.")
    parser.add_argument("--force", action="store_true", help="Re-process all files, even ones seen before.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--lang", default="eng+nep",
                         help="Tesseract OCR language(s) for scanned PDFs/images, '+' separated "
                              "(default: eng+nep). Requires the matching language packs to be "
                              "installed - see README.")
    args = parser.parse_args()

    manifest = {} if args.force else load_manifest()

    all_paths = sorted(
        p for p in glob.glob(os.path.join(INPUT_DIR, "*"))
        if os.path.splitext(p)[1].lower() in SUPPORTED_EXTENSIONS
    )

    if not all_paths:
        print(f"No resumes found in '{INPUT_DIR}/'. Add PDF/DOCX/image files and re-run.")
        sys.exit(0)

    log_rows = []
    run_start = time.perf_counter()

    for path in all_paths:
        filename = os.path.basename(path)
        h = file_hash(path)

        if h in manifest:
            print(f"Skipping (already processed): {filename}")
            continue

        print(f"Processing: {filename}")
        row = process_file(path, model=args.model, ocr_lang=args.lang)
        log_rows.append(row)
        print(f"  -> {row['status']} in {row['duration_sec']}s - {row['message']}")

        if row["status"] == "success":
            manifest[h] = {"file": filename, "candidate_id": row["candidate_id"]}

    save_manifest(manifest)

    total_duration = round(time.perf_counter() - run_start, 3)
    os.makedirs(LOG_DIR, exist_ok=True)

    if log_rows:
        log_df = pd.DataFrame(log_rows)
        log_path = os.path.join(LOG_DIR, f"ingest_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        log_df.to_excel(log_path, index=False)
        print(f"\nDone in {total_duration}s. {len(log_rows)} file(s) processed this run.")
        print(f"Log written to: {log_path}")
        print(log_df[["file", "status", "duration_sec", "message"]].to_string(index=False))
    else:
        print(f"\nNothing new to process (all {len(all_paths)} file(s) already ingested). Use --force to redo them.")


if __name__ == "__main__":
    main()