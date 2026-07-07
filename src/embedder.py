"""
embedder.py

Wraps a local sentence-transformers model + a persistent Chroma collection,
so the rest of the codebase just calls upsert()/query() without knowing
about embeddings at all.

Everything here runs fully offline once the model has been downloaded once
(sentence-transformers caches it under ~/.cache/huggingface the first time
you run this).

How search actually works here (and why):

  Chroma's query() returns the k *nearest* vectors - "nearest" is not the
  same as "relevant". With a small candidate pool, it will happily hand back
  every candidate you have even if none of them are a good fit, because
  there's nothing closer to return instead. Two things fix that, and both
  are standard in production semantic search, not something specific to
  this project:

  1. A relevance threshold (MIN_SCORE). Anything below it gets dropped
     rather than shown as a "match" at a misleadingly low score.

  2. Hybrid scoring: pure dense-embedding similarity from a small general
     model like MiniLM can under-rate exact skill/keyword matches (e.g. it
     might not clearly separate "Flutter" from "React Native" as strongly
     as a recruiter would want). So the final score blends:
       - semantic similarity (cosine similarity from the embedding), and
       - keyword overlap (what fraction of the meaningful words in the
         query literally appear in the candidate's text)
     This is the same idea production systems call "hybrid search" (dense
     vectors + sparse/keyword signal), just implemented simply instead of
     pulling in a separate search engine like Elasticsearch/BM25.
"""

import re

import chromadb
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_STORE_DIR = "data/vector_store"
COLLECTION_NAME = "candidates"

# Tuned for all-MiniLM-L6-v2 cosine similarity on short resume/job-requirement
# text. If you swap embedding models, re-check this against real queries -
# different models have different similarity distributions.
DEFAULT_MIN_SCORE = 0.35
DEFAULT_SEMANTIC_WEIGHT = 0.65  # remaining weight goes to keyword overlap

_STOPWORDS = {
    "a", "an", "the", "with", "and", "or", "of", "in", "on", "for", "to", "at",
    "is", "are", "be", "as", "who", "years", "year", "experience", "developer",
    "looking", "need", "needed", "someone", "candidate", "must", "have", "has",
}

_model = None
_client = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        print(f"Loading embedding model '{EMBEDDING_MODEL_NAME}' (first run downloads it)...")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=VECTOR_STORE_DIR)
        _collection = _client.get_or_create_collection(name=COLLECTION_NAME)
    return _collection


def embed_text(text: str):
    model = _get_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def upsert_candidate(candidate_id: str, embedding_text: str, metadata: dict):
    """Add or update a candidate's vector + metadata in the store."""
    collection = _get_collection()
    vector = embed_text(embedding_text)
    collection.upsert(
        ids=[candidate_id],
        embeddings=[vector],
        documents=[embedding_text],
        metadatas=[metadata],
    )


def candidate_count() -> int:
    """Total number of candidates currently indexed - used to tell 'nothing
    ingested yet' apart from 'nothing relevant found' in the UI."""
    return _get_collection().count()


def _keyword_overlap(query_text: str, document_text: str) -> float:
    """What fraction of the meaningful (non-stopword) words in the query
    literally appear in the candidate's document text. 1.0 = every
    significant query word was found; 0.0 = none were."""
    query_tokens = set(re.findall(r"[a-zA-Z0-9+#.]+", query_text.lower())) - _STOPWORDS
    if not query_tokens:
        return 0.0

    doc_lower = document_text.lower()
    hits = sum(1 for tok in query_tokens if tok in doc_lower)
    return hits / len(query_tokens)


def query(
    query_text: str,
    top_k: int = 10,
    min_score: float = DEFAULT_MIN_SCORE,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
):
    """Return up to top_k candidates that clear min_score, ranked by a
    blend of semantic similarity and keyword overlap. Returns [] rather
    than padding with irrelevant matches if nothing clears the bar."""
    total = candidate_count()
    if total == 0:
        return []

    collection = _get_collection()
    vector = embed_text(query_text)

    # Over-fetch from Chroma so the threshold has something real to filter -
    # asking for exactly top_k nearest would still return weak matches when
    # the pool is small. Capped at what's actually in the collection.
    fetch_n = min(max(top_k * 4, 20), total)

    results = collection.query(query_embeddings=[vector], n_results=fetch_n)

    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]

    scored = []
    for cid, dist, meta, doc in zip(ids, distances, metadatas, documents):
        semantic_score = max(0.0, round(1 - dist, 4))  # cosine distance -> similarity
        keyword_score = round(_keyword_overlap(query_text, doc), 4)
        final_score = round(
            semantic_weight * semantic_score + (1 - semantic_weight) * keyword_score, 4
        )

        if final_score < min_score:
            continue

        scored.append({
            "candidate_id": cid,
            "score": final_score,
            "semantic_score": semantic_score,
            "keyword_score": keyword_score,
            "metadata": meta,
            "document": doc,
        })

    scored.sort(key=lambda r: -r["score"])
    return scored[:top_k]


def delete_candidate(candidate_id: str):
    collection = _get_collection()
    collection.delete(ids=[candidate_id])