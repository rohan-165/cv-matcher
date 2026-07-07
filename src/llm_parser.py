"""
llm_parser.py

Sends raw resume text to a local Ollama model and asks it to return
structured JSON (name, email, skills, experience, etc). Ollama must
already be running locally (`ollama serve`, usually automatic once
installed) with the model pulled, e.g.:

    ollama pull qwen2.5-coder:3b

If the model returns something that isn't valid JSON (small local models
occasionally wrap output in prose or markdown fences), we try a couple of
cleanup passes before giving up and falling back to empty fields, so one
bad resume never kills the whole batch.
"""

import json
import re

import requests

from schema import empty_parsed_fields

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:3b"
MAX_INPUT_CHARS = 6000  # keep prompts fast on a small local model
REQUEST_TIMEOUT_SEC = 120

PROMPT_TEMPLATE = """You are a resume-parsing assistant. Read the resume text below and extract \
structured information. The resume may be written in English, Nepali (Devanagari script), or a \
mix of both - read and understand both languages. Keep names, places, and institutions in \
whichever script/language they originally appear in (don't translate or transliterate them). \
For free-text fields like "summary" and "description", write in English regardless of the \
source language, so results stay easy to scan and search consistently.

Respond with ONLY a single valid JSON object, no markdown fences, no commentary before or after it.

Use exactly this schema (use null or [] when information is missing, never invent data):

{{
  "full_name": string or null,
  "email": string or null,
  "phone": string or null,
  "location": string or null,
  "summary": string or null,
  "total_experience_years": number or null,
  "skills": [string, ...],
  "education": [{{"degree": string, "institution": string, "year": string}}, ...],
  "experience": [{{"title": string, "company": string, "duration": string, "description": string}}, ...],
  "certifications": [string, ...],
  "languages": [string, ...]
}}

Resume text:
\"\"\"
{resume_text}
\"\"\"

JSON:"""


def _clean_json_text(text: str) -> str:
    """Strip markdown code fences and any leading/trailing prose the model
    might add around the JSON object."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text.strip()).strip()

    # If there's stray text before/after, grab the outermost {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return text


def parse_resume_fields(raw_text: str, model: str = DEFAULT_MODEL) -> dict:
    """Call the local Ollama model and return a dict matching schema.empty_parsed_fields().
    Falls back to empty fields (never raises) so ingestion keeps moving."""
    if not raw_text.strip():
        return empty_parsed_fields()

    prompt = PROMPT_TEMPLATE.format(resume_text=raw_text[:MAX_INPUT_CHARS])

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1},
            },
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
        model_output = response.json().get("response", "")
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Could not reach Ollama at http://localhost:11434 - "
            "make sure Ollama is running (`ollama serve`) and the model is pulled "
            f"(`ollama pull {model}`)."
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Ollama request failed: {e}")

    cleaned = _clean_json_text(model_output)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Give up gracefully - keep raw_text so nothing is lost, just skip structuring
        fallback = empty_parsed_fields()
        fallback["summary"] = "(LLM parsing failed - raw text preserved, review manually)"
        return fallback

    # Merge onto defaults so missing keys don't break downstream code
    result = empty_parsed_fields()
    result.update({k: v for k, v in parsed.items() if k in result})
    return result