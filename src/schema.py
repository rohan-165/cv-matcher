"""
schema.py

Defines the shape of a "candidate record" - the JSON object we store per
resume. Having one place that builds this dict keeps ingest.py, the LLM
parser, and the search tool all in agreement about field names.
"""

from datetime import datetime


def empty_parsed_fields() -> dict:
    """Default/fallback values used when the LLM fails to return valid JSON,
    so the pipeline never crashes and always produces a record."""
    return {
        "full_name": None,
        "email": None,
        "phone": None,
        "location": None,
        "summary": None,
        "total_experience_years": None,
        "skills": [],
        "education": [],
        "experience": [],
        "certifications": [],
        "languages": [],
    }


def build_candidate_record(
    candidate_id: str,
    source_file: str,
    file_type: str,
    raw_text: str,
    parsed_fields: dict,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "source_file": source_file,
        "file_type": file_type,
        "ingested_at": datetime.now().isoformat(timespec="seconds"),
        "raw_text": raw_text,
        "parsed": parsed_fields,
    }


def build_embedding_text(record: dict) -> str:
    """Flatten the useful parsed fields (+ raw text) into one blob of text
    that gets embedded for semantic search. Weighted toward skills and
    experience since that's what recruiters search by."""
    p = record["parsed"]
    parts = []

    if p.get("full_name"):
        parts.append(f"Name: {p['full_name']}")
    if p.get("summary"):
        parts.append(f"Summary: {p['summary']}")
    if p.get("skills"):
        parts.append("Skills: " + ", ".join(p["skills"]))
    if p.get("total_experience_years") is not None:
        parts.append(f"Total experience: {p['total_experience_years']} years")

    for exp in p.get("experience", []):
        title = exp.get("title", "")
        company = exp.get("company", "")
        duration = exp.get("duration", "")
        desc = exp.get("description", "")
        parts.append(f"Experience: {title} at {company} ({duration}). {desc}")

    for edu in p.get("education", []):
        degree = edu.get("degree", "")
        institution = edu.get("institution", "")
        year = edu.get("year", "")
        parts.append(f"Education: {degree}, {institution} ({year})")

    if p.get("certifications"):
        parts.append("Certifications: " + ", ".join(p["certifications"]))
    if p.get("languages"):
        parts.append("Languages: " + ", ".join(p["languages"]))

    # Fall back to raw text if the LLM extraction gave us nothing usable
    if not parts:
        return record["raw_text"][:3000]

    return "\n".join(parts)
