# CV Matcher — Local Resume Intake & Candidate Search

Drop resumes (PDF, DOCX, or images) into `input/`. Fully local, nothing leaves
your machine. For each resume, the pipeline:

1. **Extracts text** — native PDF/DOCX text, or OCR for scans/images (English
   + Nepali by default, other languages configurable)
2. **Pulls out structured fields** — name, email, phone, skills, education,
   experience — using a **local LLM via Ollama** (no cloud API, no per-resume
   cost)
3. **Saves a JSON record** per candidate in `data/candidates/`
4. **Embeds it into a local vector index**, so you can later search
   *"Flutter developer with BLE experience"* and get ranked, relevant matches
   — from the command line or a browser page

Everything runs on your own machine: text extraction, LLM parsing (Ollama),
and embeddings/search (sentence-transformers + Chroma) are all local. No
resume data is sent to any third-party API.

---

## Contents

- [Prerequisites](#prerequisites)
- [Setup — macOS](#setup--macos)
- [Setup — Linux](#setup--linux)
- [Setup — Windows](#setup--windows)
- [Usage](#usage)
- [How search relevance works](#how-search-relevance-works)
- [Project structure](#project-structure)
- [Candidate JSON shape](#candidate-json-shape)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)

---

## Prerequisites

| Requirement | Why | Notes |
|---|---|---|
| Python 3.10–3.13 | Runs the whole pipeline | 3.14 works too, but very new Python versions can hit dependency-resolution issues — see [Troubleshooting](#troubleshooting) |
| [Ollama](https://ollama.com/download) | Local LLM that turns raw resume text into structured JSON | Free, runs offline once the model is pulled |
| Tesseract OCR (+ language data) | Reads text out of scanned/photographed resumes | Plain Tesseract is English-only — you need the language-pack variant for Nepali/other scripts |
| ~2 GB free disk | `sentence-transformers` pulls in PyTorch | One-time; the embedding model itself is only ~90 MB |

---

## Setup — macOS

**1. Install Ollama and pull a model**
```bash
brew install ollama
ollama serve &                 # starts the local Ollama server (skip if you installed the Ollama.app instead)
ollama pull qwen2.5-coder:3b   # ~2GB download, one-time
```

**2. Install Tesseract with full language support**
```bash
brew install tesseract-lang
tesseract --list-langs   # confirm "eng" and "nep" both appear
```
(`brew install tesseract` alone only gives you English — use `tesseract-lang`.)

**3. Clone and set up the project**
```bash
git clone <this-repo-url> cv-matcher
cd cv-matcher
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ml.txt
```

You're ready — jump to [Usage](#usage).

---

## Setup — Linux

**1. Install Ollama and pull a model**
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &                 # or: systemctl --user start ollama, if installed as a service
ollama pull qwen2.5-coder:3b
```

**2. Install Tesseract with language data**

Debian/Ubuntu:
```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-nep
```
Fedora:
```bash
sudo dnf install tesseract tesseract-langpack-nep
```
Arch:
```bash
sudo pacman -S tesseract tesseract-data-nep tesseract-data-eng
```
Then confirm:
```bash
tesseract --list-langs
```

**3. Clone and set up the project**
```bash
git clone <this-repo-url> cv-matcher
cd cv-matcher
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ml.txt
```

You're ready — jump to [Usage](#usage).

---

## Setup — Windows

Use **PowerShell** for all of this.

**1. Install Ollama and pull a model**

Download and run the installer from [ollama.com/download](https://ollama.com/download).
Ollama runs as a background service automatically once installed — no
separate "serve" step needed.
```powershell
ollama pull qwen2.5-coder:3b
```

**2. Install Tesseract with language data**

Download the installer from the
[UB-Mannheim Tesseract build](https://github.com/UB-Mannheim/tesseract/wiki)
(the standard Windows distribution) and, during install, make sure to check
**"Nepali"** (and any other language you need) under "Additional language data" —
it's unchecked by default.

After installing, add Tesseract to your PATH (the installer usually offers
to do this; if not, add `C:\Program Files\Tesseract-OCR` to your PATH
environment variable), then confirm in a new PowerShell window:
```powershell
tesseract --list-langs
```

**3. Clone and set up the project**
```powershell
git clone <this-repo-url> cv-matcher
cd cv-matcher
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ml.txt
```

> If PowerShell blocks the activation script with an execution-policy error,
> run this once (as your normal user, not admin):
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

You're ready — jump to [Usage](#usage).

---

## Usage

### 1. Ingest resumes

```bash
python3 ingest.py          # macOS/Linux
python ingest.py           # Windows
```

- Drop CVs into `input/` any time and re-run — already-processed files are
  skipped automatically (tracked by content hash in `data/manifest.json`).
- `--force` re-processes everything (e.g. after changing the extraction prompt).
- `--model <name>` uses a different Ollama model (default: `qwen2.5-coder:3b`).
- `--lang eng+nep` (default) controls OCR languages for scanned PDFs/images —
  `+`-separated Tesseract language codes, e.g. `--lang eng+hin` for Hindi instead.
- Each run writes a log to `output/ingest_log_<timestamp>.xlsx` (status,
  duration, and any errors per file).

### 2. Search from the command line

```bash
python3 search.py "Flutter developer with BLE and wearable SDK experience"
python3 search.py "iOS developer, Swift, 3+ years" --top 5
python3 search.py "backend developer Python Django" --export shortlist.xlsx
python3 search.py "React Native developer" --min-score 0.5   # stricter cutoff
```

### 3. Search from a browser

```bash
python3 webapp/server.py
```
Open **http://127.0.0.1:8765**. Type a role description, see ranked candidates
with a match score and breakdown, tick the ones you want, click **"View full
details"** for the full parsed record, and **"Export selected to Excel"** to
download a shortlist. Bound to `127.0.0.1` only — not exposed to your network.

To stop it: `Ctrl+C` in its terminal, or:
```bash
lsof -ti:8765 | xargs kill      # macOS/Linux
```
```powershell
Get-Process -Id (Get-NetTCPConnection -LocalPort 8765).OwningProcess | Stop-Process   # Windows
```

---

## How search relevance works

Chroma's vector search returns the *k nearest* candidates — "nearest" isn't
the same as "relevant". With a small candidate pool, it will hand back every
candidate you have even when none of them fit, because there's nothing closer
to return instead. Two standard techniques fix that:

1. **A relevance threshold** (`--min-score`, default `0.35`). Anything below
   it is dropped rather than shown as a match at a misleadingly low score.
   If nothing clears the bar, you get a clear "no relevant candidates found"
   instead of a list padded with irrelevant people at 0%.

2. **Hybrid scoring**. A small general-purpose embedding model
   (`all-MiniLM-L6-v2`) can under-rate exact skill matches. The final score
   blends:
   - **semantic similarity** — cosine similarity between the job requirement
     and the candidate's embedded profile
   - **keyword overlap** — what fraction of the meaningful words in your
     query literally appear in the candidate's record

   This is the same idea production systems call "hybrid search" (dense
   vectors + a keyword/sparse signal), just implemented simply here instead
   of adding a separate search engine.

If you're not finding anyone, lower `--min-score` (or pick "Loose" in the web
UI). If you're getting too many loose matches, raise it.

---

## Project structure

```
cv-matcher/
├── input/                     # drop CVs here (pdf, docx, png/jpg, ...)
├── data/
│   ├── candidates/            # one JSON file per candidate
│   ├── manifest.json          # tracks which files have been ingested
│   └── vector_store/          # local Chroma database (embeddings)
├── output/                    # ingest logs + exported shortlists
├── src/
│   ├── extractors.py          # PDF / DOCX / image -> raw text (+ OCR)
│   ├── llm_parser.py          # raw text -> structured JSON (via Ollama)
│   ├── schema.py               # candidate record shape + embedding text builder
│   └── embedder.py             # sentence-transformers + Chroma + hybrid search
├── ingest.py                   # main pipeline entrypoint
├── search.py                    # search CLI
├── webapp/
│   ├── server.py                 # Flask API + serves index.html
│   └── index.html                 # browser search UI
├── requirements.txt                # lightweight deps (extraction, Excel, Flask)
└── requirements-ml.txt              # embeddings/vector search (installed separately)
```

---

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

---

## Configuration reference

| Flag / setting | Where | Default | Purpose |
|---|---|---|---|
| `--model` | `ingest.py` | `qwen2.5-coder:3b` | Ollama model used for field extraction |
| `--lang` | `ingest.py` | `eng+nep` | Tesseract OCR language(s), `+`-separated |
| `--force` | `ingest.py` | off | Re-process all files, ignoring the manifest |
| `--top` | `search.py` | `10` | Max number of results to return |
| `--min-score` | `search.py` | `0.35` | Relevance threshold (0–1) |
| `--export` | `search.py` | none | Export ranked results to an `.xlsx` file |
| `OCR_LANGUAGES` | `src/extractors.py` | `"eng+nep"` | Change the project-wide default OCR languages |
| `DEFAULT_MIN_SCORE` / `DEFAULT_SEMANTIC_WEIGHT` | `src/embedder.py` | `0.35` / `0.65` | Tune the relevance bar and the semantic-vs-keyword blend |
| `EMBEDDING_MODEL_NAME` | `src/embedder.py` | `all-MiniLM-L6-v2` | Swap the local embedding model |

---

## Troubleshooting

**`error: the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version`**
(building `tokenizers` from source fails)
→ This happens when `pip` resolves an old `tokenizers` version that has no
prebuilt wheel for a very new Python release, so it tries to compile it with
Rust, which fails. Fix: `pip install --upgrade tokenizers` before installing
`requirements-ml.txt`, or install Python 3.11–3.13 for this project instead
of a bleeding-edge release.

**`Cannot install ... because these package versions have conflicting dependencies` (Pillow)**
→ Run `pip install --upgrade pillow` first, then re-run the requirements
install — `pdfplumber` needs a newer Pillow than some older pins expect.

**`error: resolution-too-deep`**
→ pip's resolver hit a very deep dependency tree. This is exactly why
`requirements-ml.txt` is installed as a *separate* command from
`requirements.txt` — if you combined them into one `pip install`, split them
back into two. If it still happens on the ML file alone, try pinning
`sentence-transformers` to one specific recent version rather than a range.

**`Could not reach Ollama at http://localhost:11434`**
→ Ollama isn't running. macOS/Linux: `ollama serve` in a terminal (or check
`ollama.app`/systemd service is running). Windows: check the Ollama icon is
running in your system tray; reinstall if it's missing.

**OCR misses Nepali (or other non-English) text entirely**
→ You installed plain `tesseract` instead of the language-pack variant, or
didn't select the language during the Windows installer. Re-check the
[Setup](#setup--macos) section for your OS. `extractors.py` will also print
a one-time warning naming exactly which language pack is missing.

**Search returns nothing / too few results**
→ Lower `--min-score` (or "Loose" in the web UI). With a very small candidate
pool, strict thresholds can filter out everyone.

**`No space left on device` while installing `requirements-ml.txt`**
→ `sentence-transformers` pulls in PyTorch (~2GB). Free up disk space before
retrying.

---

## Known limitations

- **Legacy `.doc` files** (old binary Word format) aren't supported directly
  — re-save as `.docx` or export to PDF first.
- **OCR quality** depends on scan quality — clean scans/photos work well;
  blurry or skewed photos may need better lighting/cropping.
- **Small local LLMs occasionally mis-extract a field** (e.g. miss a phone
  number in an unusual format). `raw_text` is always preserved in the JSON,
  so nothing is lost — you can spot-check or correct manually.
- **Match scores are a ranking signal, not gospel** — always skim the actual
  skills/summary before shortlisting a candidate.
- The first `ingest.py` run downloads the `all-MiniLM-L6-v2` embedding model
  (~90 MB) — after that, everything runs fully offline.