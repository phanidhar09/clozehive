"""Metadata-aware reranking for RAG retrieval results."""

from __future__ import annotations

import re
from typing import Any


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _text_overlap(a: str, b: str) -> bool:
    a_norm, b_norm = _normalize(a), _normalize(b)
    if not a_norm or not b_norm:
        return False
    if a_norm in b_norm or b_norm in a_norm:
        return True
    return bool(set(a_norm.split()) & set(b_norm.split()))


def rerank_fashion_documents(
    docs: list[dict[str, Any]],
    *,
    occasion: str | None = None,
    season: str | None = None,
    weather: str | None = None,
) -> list[dict[str, Any]]:
    if not docs:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in docs:
        score = float(doc.get("relevance_score", 0))
        doc_occ = doc.get("occasion") or ""
        doc_season = doc.get("season") or ""
        doc_cat = doc.get("category") or ""

        if occasion and doc_occ and _text_overlap(occasion, doc_occ):
            score += 0.12
        elif occasion and doc_occ and _text_overlap(occasion, doc_occ.split()[0]):
            score += 0.08

        if season and doc_season and _text_overlap(season, doc_season):
            score += 0.08

        if weather:
            if weather == "rain" and doc_cat == "weather":
                score += 0.10
            if _text_overlap(weather, doc.get("title", "")):
                score += 0.06
            if _text_overlap(weather, doc.get("content", "")[:200]):
                score += 0.04

        if occasion and _text_overlap(occasion, doc.get("title", "")):
            score += 0.05

        scored.append((score, {**doc, "relevance_score": round(min(1.0, score), 3)}))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored]


def rerank_outfit_history(
    records: list[dict[str, Any]],
    *,
    occasion: str | None = None,
) -> list[dict[str, Any]]:
    if not records:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for rec in records:
        score = float(rec.get("similarity_score", 0))
        rec_occ = rec.get("occasion") or ""
        if occasion and rec_occ and _text_overlap(occasion, rec_occ):
            score += 0.12
        elif occasion and rec_occ and occasion.lower() == rec_occ.lower():
            score += 0.15

        if rec.get("was_worn"):
            score += 0.06
        if rec.get("was_saved"):
            score += 0.04

        matching = rec.get("matching_score")
        if isinstance(matching, int) and matching >= 80:
            score += 0.03
        elif isinstance(matching, int) and matching >= 70:
            score += 0.02

        if rec.get("user_feedback"):
            score += 0.02

        scored.append((score, {**rec, "similarity_score": round(min(1.0, score), 3)}))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in scored]


def rerank_packing_memories(
    records: list[dict[str, Any]],
    *,
    purpose: str,
    destination: str,
) -> list[dict[str, Any]]:
    if not records:
        return []

    dest_norm = _normalize(destination)
    scored: list[tuple[float, dict[str, Any]]] = []
    for rec in records:
        score = float(rec.get("similarity_score", 0))
        rec_purpose = rec.get("purpose") or ""
        rec_dest = _normalize(rec.get("destination") or "")

        if rec_purpose and _text_overlap(purpose, rec_purpose):
            score += 0.10
        elif rec_purpose and purpose.lower() == rec_purpose.lower():
            score += 0.12

        if rec_dest and dest_norm:
            if dest_norm in rec_dest or rec_dest in dest_norm:
                score += 0.08
            elif set(dest_norm.split()) & set(rec_dest.split()):
                score += 0.05

        if rec.get("missing_items"):
            score += 0.02
        if rec.get("user_feedback"):
            score += 0.02

        scored.append((score, {**rec, "similarity_score": round(min(1.0, score), 3)}))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in scored]
