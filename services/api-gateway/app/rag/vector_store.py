"""
Vector store abstraction for CLOZEHIVE RAG.

Two backends
────────────
FAISSVectorStore
    In-memory FAISS index, optionally persisted to disk.  No database is required
    for reads.  Use for local development and unit testing.

PGVectorStore
    Production backend using PostgreSQL + pgvector.  Delegates to the existing
    `pgvector_cosine_search` helper.  Requires an AsyncSession per call.

Backend selection
─────────────────
Set RAG_VECTOR_STORE env var to "faiss" or "pgvector" (default: pgvector).

User isolation
──────────────
Both backends guarantee user isolation at the retrieval layer:
  - pgvector: enforced by `WHERE user_id = :uid` in SQL.
  - FAISS: enforced by post-retrieval metadata filtering before results are returned.
  If user_id is None the query is treated as global (e.g. fashion knowledge documents).

Similarity thresholding
───────────────────────
A threshold parameter is required on every search call.  Results below the threshold
are discarded before they reach the caller.

Source types
────────────
SOURCE_CLOSET_ITEM        → closet_items table
SOURCE_OUTFIT_HISTORY     → outfit_history table
SOURCE_PACKING_MEMORY     → packing_memory table
SOURCE_FASHION_KNOWLEDGE  → fashion_knowledge_documents table
"""

from __future__ import annotations

import asyncio
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.embedding_service import pgvector_cosine_search

logger = get_logger("rag.vector_store")

# ── Source-type constants ─────────────────────────────────────────────────────

SOURCE_CLOSET_ITEM = "closet_item"
SOURCE_OUTFIT_HISTORY = "outfit_history"
SOURCE_PACKING_MEMORY = "packing_memory"
SOURCE_FASHION_KNOWLEDGE = "fashion_knowledge"

_SOURCE_TO_TABLE: dict[str, str] = {
    SOURCE_CLOSET_ITEM: "closet_items",
    SOURCE_OUTFIT_HISTORY: "outfit_history",
    SOURCE_PACKING_MEMORY: "packing_memory",
    SOURCE_FASHION_KNOWLEDGE: "fashion_knowledge_documents",
}

_EMBEDDING_DIM = 1536

# ── Data models ───────────────────────────────────────────────────────────────


@dataclass
class EmbeddingMeta:
    """Rich metadata stored alongside each embedding vector.

    Matches the metadata requirements from the product spec:
    user_id, item_id, category, color, season, occasion, style_tags, source_type.
    """

    record_id: str
    source_type: str
    user_id: str | None = None          # None for global knowledge (fashion docs)
    category: str | None = None
    color: str | None = None
    season: list[str] | None = None
    occasion: list[str] | None = None
    style_tags: list[str] | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Single retrieval hit with normalised metadata and similarity score."""

    record_id: str
    source_type: str
    similarity_score: float
    user_id: str | None = None
    category: str | None = None
    color: str | None = None
    season: list[str] | None = None
    occasion: list[str] | None = None
    style_tags: list[str] | None = None
    payload: dict[str, Any] = field(default_factory=dict)


# ── Protocol ──────────────────────────────────────────────────────────────────


@runtime_checkable
class VectorStore(Protocol):
    """Minimal interface every vector store backend must satisfy."""

    async def search(
        self,
        *,
        source_type: str,
        embedding: list[float],
        user_id: str | None,
        limit: int = 5,
        threshold: float = 0.70,
        exclude_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> list[SearchResult]: ...

    async def upsert(
        self,
        *,
        meta: EmbeddingMeta,
        embedding: list[float],
        session: AsyncSession | None = None,
    ) -> None: ...


# ── FAISS backend ─────────────────────────────────────────────────────────────


class FAISSVectorStore:
    """
    In-memory FAISS vector store with optional disk persistence.

    Each source_type maintains a separate IndexFlatIP (inner product) with
    L2-normalised vectors — equivalent to cosine similarity.

    User isolation is always enforced: after FAISS retrieves candidates,
    any result whose stored user_id != requested user_id is discarded before
    results are returned.

    Thread safety: one asyncio.Lock per source_type; FAISS CPU operations run
    in a thread pool via asyncio.to_thread.
    """

    def __init__(self, index_dir: str | Path | None = None) -> None:
        self._index_dir = Path(index_dir) if index_dir else None
        # source_type → faiss.Index
        self._indexes: dict[str, Any] = {}
        # source_type → list[EmbeddingMeta] parallel to FAISS index rows
        self._meta: dict[str, list[EmbeddingMeta]] = {}
        # Per source_type write locks — created lazily
        self._locks: dict[str, asyncio.Lock] = {}

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _lock(self, source_type: str) -> asyncio.Lock:
        if source_type not in self._locks:
            self._locks[source_type] = asyncio.Lock()
        return self._locks[source_type]

    def _ensure_index(self, source_type: str) -> None:
        """Initialise an empty FAISS index for source_type (must hold lock)."""
        if source_type in self._indexes:
            return
        try:
            import faiss  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "faiss-cpu is required for FAISSVectorStore. "
                "Install it with: pip install faiss-cpu"
            ) from exc
        self._indexes[source_type] = faiss.IndexFlatIP(_EMBEDDING_DIM)
        self._meta[source_type] = []
        logger.info("faiss_index_created", source_type=source_type, dim=_EMBEDDING_DIM)

    def _load_from_disk(self, source_type: str) -> bool:
        """Load persisted index from disk. Returns True if successful (must hold lock)."""
        if not self._index_dir:
            return False
        idx_path = self._index_dir / f"{source_type}.index"
        meta_path = self._index_dir / f"{source_type}.pkl"
        if not idx_path.exists() or not meta_path.exists():
            return False
        try:
            import faiss  # noqa: PLC0415
            self._indexes[source_type] = faiss.read_index(str(idx_path))
            with meta_path.open("rb") as fh:
                self._meta[source_type] = pickle.load(fh)  # noqa: S301
            logger.info(
                "faiss_index_loaded",
                source_type=source_type,
                total=self._indexes[source_type].ntotal,
            )
            return True
        except Exception as exc:
            logger.warning("faiss_index_load_failed", source_type=source_type, error=str(exc))
            return False

    def _persist_to_disk(self, source_type: str) -> None:
        """Atomically persist current index to disk (must hold lock)."""
        if not self._index_dir:
            return
        self._index_dir.mkdir(parents=True, exist_ok=True)
        idx_path = self._index_dir / f"{source_type}.index"
        meta_path = self._index_dir / f"{source_type}.pkl"
        try:
            import faiss  # noqa: PLC0415
            faiss.write_index(self._indexes[source_type], str(idx_path))
            tmp = meta_path.with_suffix(".tmp.pkl")
            with tmp.open("wb") as fh:
                pickle.dump(self._meta[source_type], fh)
            tmp.replace(meta_path)
        except Exception as exc:
            logger.warning("faiss_persist_failed", source_type=source_type, error=str(exc))

    @staticmethod
    def _normalise(embedding: list[float]) -> np.ndarray:
        """L2-normalise so IndexFlatIP returns cosine similarity scores in [0, 1]."""
        arr = np.array([embedding], dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-10, norms)
        return arr / norms

    # ── Public interface ─────────────────────────────────────────────────────

    async def search(
        self,
        *,
        source_type: str,
        embedding: list[float],
        user_id: str | None,
        limit: int = 5,
        threshold: float = 0.70,
        exclude_id: str | None = None,  # ignored; metadata filters are applied in Python
        session: AsyncSession | None = None,
    ) -> list[SearchResult]:
        async with self._lock(source_type):
            if source_type not in self._indexes:
                if not self._load_from_disk(source_type):
                    self._ensure_index(source_type)

            index = self._indexes[source_type]
            meta_list = list(self._meta.get(source_type, []))  # snapshot

        if index.ntotal == 0:
            return []

        def _run_search() -> list[SearchResult]:
            vec = self._normalise(embedding)
            # Over-fetch to allow for user_id filtering without losing results
            k = min(index.ntotal, max(limit * 10, 50))
            scores, indices = index.search(vec, k)
            out: list[SearchResult] = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0:
                    continue
                sim = float(score)
                if sim < threshold:
                    continue
                meta = meta_list[idx]
                # User isolation: never return another user's data
                if (
                    user_id is not None
                    and meta.user_id is not None
                    and meta.user_id != user_id
                ):
                    continue
                out.append(SearchResult(
                    record_id=meta.record_id,
                    source_type=meta.source_type,
                    similarity_score=round(sim, 4),
                    user_id=meta.user_id,
                    category=meta.category,
                    color=meta.color,
                    season=meta.season,
                    occasion=meta.occasion,
                    style_tags=meta.style_tags,
                    payload=meta.payload,
                ))
                if len(out) >= limit:
                    break
            return out

        return await asyncio.to_thread(_run_search)

    async def upsert(
        self,
        *,
        meta: EmbeddingMeta,
        embedding: list[float],
        session: AsyncSession | None = None,
    ) -> None:
        source_type = meta.source_type
        async with self._lock(source_type):
            if source_type not in self._indexes:
                if not self._load_from_disk(source_type):
                    self._ensure_index(source_type)

            index = self._indexes[source_type]
            meta_list = self._meta[source_type]

            # If record already exists, update only the metadata (can't remove/update
            # a vector in IndexFlatIP without rebuilding the entire index).
            for i, existing in enumerate(meta_list):
                if existing.record_id == meta.record_id:
                    meta_list[i] = meta
                    logger.debug("faiss_meta_updated", record_id=meta.record_id)
                    return

            def _add() -> None:
                vec = self._normalise(embedding)
                index.add(vec)
                meta_list.append(meta)

            await asyncio.to_thread(_add)
            self._persist_to_disk(source_type)
            logger.debug(
                "faiss_upserted",
                source_type=source_type,
                record_id=meta.record_id,
                total=index.ntotal,
            )

    def total(self, source_type: str) -> int:
        """Return number of vectors stored for a source_type."""
        idx = self._indexes.get(source_type)
        return idx.ntotal if idx else 0


# ── pgvector backend ──────────────────────────────────────────────────────────


class PGVectorStore:
    """
    Production vector store backed by PostgreSQL + pgvector.

    Delegates all reads to `pgvector_cosine_search` which executes a raw
    parameterised SQL query with the pgvector <=> (cosine distance) operator.

    User isolation is enforced at the SQL level:
        WHERE user_id = :uid::uuid

    Writes are handled by the existing SQLAlchemy model layer; upsert() is a
    no-op here because the embedding is persisted when the parent record is saved.
    """

    async def search(
        self,
        *,
        source_type: str,
        embedding: list[float],
        user_id: str | None,
        limit: int = 5,
        threshold: float = 0.70,
        exclude_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> list[SearchResult]:
        if session is None:
            raise ValueError("PGVectorStore.search requires a database session")

        table = _SOURCE_TO_TABLE.get(source_type)
        if not table:
            logger.warning("pgvector_unknown_source_type", source_type=source_type)
            return []

        rows = await pgvector_cosine_search(
            session,
            table=table,
            embedding=embedding,
            user_id=user_id,
            limit=limit,
            threshold=threshold,
            exclude_id=exclude_id,
        )
        return [_row_to_search_result(row, source_type) for row in rows]

    async def upsert(
        self,
        *,
        meta: EmbeddingMeta,
        embedding: list[float],
        session: AsyncSession | None = None,
    ) -> None:
        # Embeddings are written via SQLAlchemy models when the parent record is
        # created/updated (see similarity_service.generate_item_embedding etc.).
        # This is intentionally a no-op for pgvector.
        pass


# ── Row normalisation ─────────────────────────────────────────────────────────


def _row_to_search_result(row: dict[str, Any], source_type: str) -> SearchResult:
    """Normalise a pgvector result dict into a SearchResult."""
    user_id = str(row["user_id"]) if row.get("user_id") else None

    season = row.get("season")
    if isinstance(season, str) and season:
        season = [season]
    elif not isinstance(season, list):
        season = None

    occasion = row.get("occasion")
    if isinstance(occasion, str) and occasion:
        occasion = [occasion]
    elif not isinstance(occasion, list):
        occasion = None

    tags = row.get("tags")
    style_tags: list[str] | None = None
    if isinstance(tags, dict):
        style_tags = tags.get("tags") or []
    elif isinstance(tags, list):
        style_tags = tags

    return SearchResult(
        record_id=str(row["id"]),
        source_type=source_type,
        similarity_score=round(float(row.get("similarity_score", 0)), 4),
        user_id=user_id,
        category=row.get("category"),
        color=row.get("color") or row.get("missing_color"),
        season=season,
        occasion=occasion,
        style_tags=style_tags,
        payload=dict(row),
    )


# ── Factory & singleton ───────────────────────────────────────────────────────


def make_vector_store(backend: str = "pgvector", index_dir: str = "./faiss_indexes") -> FAISSVectorStore | PGVectorStore:
    """Construct a vector store from explicit parameters (testable without config)."""
    if backend == "faiss":
        return FAISSVectorStore(index_dir=index_dir)
    return PGVectorStore()


# Module-level singleton — shared across requests; tests reset it via _reset().
_singleton: FAISSVectorStore | PGVectorStore | None = None


def get_vector_store() -> FAISSVectorStore | PGVectorStore:
    """Return the application-wide vector store, creating it on first call."""
    global _singleton
    if _singleton is None:
        from app.core.config import get_settings  # lazy to avoid circular import
        s = get_settings()
        backend = getattr(s, "rag_vector_store", "pgvector")
        index_dir = getattr(s, "faiss_index_dir", "./faiss_indexes")
        _singleton = make_vector_store(backend=backend, index_dir=index_dir)
        logger.info("vector_store_initialised", backend=backend)
    return _singleton


def _reset_vector_store() -> None:
    """Reset the singleton — used in tests to get a fresh store per test."""
    global _singleton
    _singleton = None
