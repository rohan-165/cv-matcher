"""
embedder.py

Wraps a local sentence-transformers model + a persistent Chroma collection,
so the rest of the codebase just calls upsert()/query() without knowing
about embeddings at all.

Everything here runs fully offline once the model has been downloaded once
(sentence-transformers caches it under ~/.cache/huggingface the first time
you run this).
"""

import chromadb
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_STORE_DIR = "data/vector_store"
COLLECTION_NAME = "candidates"

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


def query(query_text: str, top_k: int = 10):
    """Return top_k most similar candidates as a list of dicts:
    {candidate_id, score, metadata, document}"""
    collection = _get_collection()
    vector = embed_text(query_text)

    results = collection.query(
        query_embeddings=[vector],
        n_results=top_k,
    )

    output = []
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]

    for cid, dist, meta, doc in zip(ids, distances, metadatas, documents):
        # Chroma returns cosine *distance*; convert to a 0-1 similarity score
        similarity = round(1 - dist, 4)
        output.append({
            "candidate_id": cid,
            "score": similarity,
            "metadata": meta,
            "document": doc,
        })

    return output


def delete_candidate(candidate_id: str):
    collection = _get_collection()
    collection.delete(ids=[candidate_id])
