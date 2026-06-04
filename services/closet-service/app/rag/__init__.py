"""
RAG (Retrieval-Augmented Generation) module for CLOZEHIVE.

Sub-modules:
    vector_store  — Abstract VectorStore protocol, FAISSVectorStore, PGVectorStore.
    retriever     — High-level retrieval orchestration for each RAG use case.
    schemas       — Pydantic request/response models for /api/v1/rag/* endpoints.

Design principles:
    - All retrieval is user-scoped: user_id is always checked at the store layer.
    - Similarity thresholds are enforced at every search call (never return junk matches).
    - Every retrieval function returns a typed fallback when no context is found
      so callers never receive an exception or null.
    - FAISSVectorStore is the default for local dev / testing (no pgvector extension needed).
    - PGVectorStore is the production backend — delegates to existing pgvector queries.
"""
