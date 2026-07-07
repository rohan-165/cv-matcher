# CV Matcher — Resume Intake & Candidate Search

Drop resumes (PDF, DOCX, or images) into `input/`. Each one gets:
1. Text extracted (native PDF/DOCX text, or OCR for scans/images)
2. Structured fields pulled out by a **local** LLM (name, email, phone, skills,
   education, experience, etc.) via Ollama — nothing leaves your machine
3. Saved as a JSON record in `data/candidates/`
4. Embedded and added to a local vector index, so you can later search
   "find me a Flutter dev with BLE experience" and get ranked matches

## One-time setup (macOS)

```bash
cd cv-matcher
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ml.txt
```

Installing in two stages like this (rather than one combined file) avoids pip's
resolver blowing up on the deep `sentence-transformers` → `huggingface-hub` →
`httpx` dependency tree when it's mixed with the lightweight extraction
libraries in a single resolve.

You also need:
- **Tesseract with English + Nepali language data** (for scanned/image resumes):
  ```bash
  brew install tesseract-lang
  tesseract --list-langs   # confirm "nep" appears in the list
  ```
  Plain `brew install tesseract` only installs English - use `tesseract-lang`
  instead, which bundles Nepali and most other scripts. If you already have
  the English-only version installed, `brew install tesseract-lang` will add
  the rest of the language data alongside it.
- **Ollama** running locally with a model pulled, e.g.:
  ```bash
  ollama pull qwen2.5-coder:3b
  ```
  (This is the same model you already use in `rohan-ai` — reused here for
  structured extraction. Ollama needs to be running — `ollama serve`, or it
  auto-starts if you installed the Mac app.)

## Usage

### 1. Ingest resumes

```bash
source .venv/bin/activate
python3 ingest.py
```

- Drop new CVs into `input/` any time and re-run — already-processed files
  are skipped automatically (tracked in `data/manifest.json` by file hash).
- Use `python3 ingest.py --force` to re-process everything (e.g. after you
  tweak the extraction prompt in `src/llm_parser.py`).
- Each run writes a log to `output/ingest_log_<timestamp>.xlsx` showing
  status, duration, and any errors per file.
- OCR (for scanned PDFs and image resumes) reads English + Nepali by default.
  Change it per run with `--lang`, e.g.:
  ```bash
  python3 ingest.py --lang eng+hin   # add Hindi instead
  python3 ingest.py --lang eng       # English only
  ```
  If a requested language pack isn't installed, you'll see one warning per
  language naming it and get told how to install it - that resume still gets
  processed with whatever languages *are* available, it just won't read the
  missing script.

### 2. Search candidates

```bash
python3 search.py "React Native developer with 3+ years, BLE experience"
python3 search.py "backend developer Python Django" --top 5
python3 search.py "iOS developer Swift Firebase" --top 10 --export shortlist.xlsx
```

`--export` saves the ranked shortlist as an Excel file in `output/` — handy
for sending straight to the requesting office.

### 3. Search from a web page (optional)

Instead of the CLI, you can search from a browser:

```bash
source .venv/bin/activate
python3 webapp/server.py
```

Then open **http://127.0.0.1:8765**. It's the same search index and candidate
JSON files as `search.py` — just a nicer view. Type a role description,
see ranked candidates with a match score, tick the ones you want, click
**"View full details"** for the full parsed record, and use **"Export
selected to Excel"** to download a shortlist straight from the browser.

The server only binds to `127.0.0.1` (your machine only) — it's not exposed
to your network.

## Project structure


```
cv-matcher/
├── input/                  # drop CVs here (pdf, docx, png/jpg, ...)
├── data/
│   ├── candidates/         # one JSON file per candidate
│   ├── manifest.json       # tracks which files have been ingested
│   └── vector_store/       # local Chroma database (embeddings)
├── output/                 # ingest logs + exported shortlists
├── src/
│   ├── extractors.py       # PDF / DOCX / image -> raw text
│   ├── llm_parser.py       # raw text -> structured JSON (via Ollama)
│   ├── schema.py            # candidate record shape + embedding text builder
│   └── embedder.py          # sentence-transformers + Chroma wrapper
├── ingest.py                # main pipeline entrypoint
├── search.py                 # search CLI
├── webapp/
│   ├── server.py              # Flask API + serves index.html
│   └── index.html              # browser search UI
└── requirements.txt
```

## Candidate JSON shape

```json
{
  "candidate_id": "uuid",
  "source_file": "resume.pdf",
  "file_type": "pdf",
  "ingested_at": "2026-07-06T12:00:00",
  "raw_text": "...full extracted text...",
  "parsed": {
    "full_name": "...",
    "email": "...",
    "phone": "...",
    "location": "...",
    "summary": "...",
    "total_experience_years": 3,
    "skills": ["Flutter", "Kotlin", "..."],
    "education": [{"degree": "...", "institution": "...", "year": "..."}],
    "experience": [{"title": "...", "company": "...", "duration": "...", "description": "..."}],
    "certifications": [],
    "languages": []
  }
}
```

## Notes & known limits

- **Legacy `.doc` files** (old binary Word format) aren't supported directly —
  re-save as `.docx` or export to PDF first. `.docx`, `.pdf`, and images all work.
- **OCR quality** depends on scan quality. Clean scans/photos work well;
  blurry or skewed photos may need better lighting/cropping.
- **Nepali/mixed-language resumes**: OCR reads English + Nepali by default
  (requires the `tesseract-lang` package, not just `tesseract` - see setup
  above). The LLM parsing step is also told to expect both languages and
  keeps names/places in their original script rather than translating them.
- **Small local LLMs occasionally mis-extract** a field (e.g. miss a phone
  number in an unusual format). `raw_text` is always preserved in the JSON,
  so you can always double check or manually correct a record without
  re-running OCR.
- The first `ingest.py` run will download the `all-MiniLM-L6-v2` embedding
  model (~90MB) — after that it's fully offline.
- Match scores from `search.py` are cosine similarity (0–1, higher = closer
  match) — treat them as a ranking signal, not an absolute cutoff. Always
  skim the actual skills/summary before shortlisting.