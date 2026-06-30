"""DB-backed verification of the knowledge-base write paths (previously only unit-tested).

Exercises the real SQLAlchemy paths against the SQLite test harness:
  - ensure_seeded: YAML corpus -> fashion_knowledge_documents, with the new
    gender/region/source metadata folded into the tags JSONB, idempotently.
  - refresh_learned_knowledge: closet items + saved outfits -> an aggregated,
    anonymised "learned" document; refresh (not duplicate) on re-run; nothing
    when data is too thin.

Embeddings are stubbed to None (the real no-API-key behaviour) so these never
touch the network.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.api.v1.intelligence.services import fashion_rag_service
from app.api.v1.intelligence.services import knowledge_mining_service as mining
from app.models.closet import ClosetItem, Outfit, WearEvent
from app.models.rag import FashionKnowledgeDocument, OutfitHistory
from app.rag.knowledge_loader import load_seed_documents


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch):
    async def _none(_text: str):
        return None

    # fashion_rag_service imports the name at module level; mining imports it lazily
    # from the source module — patch both bindings.
    monkeypatch.setattr(fashion_rag_service, "generate_text_embedding", _none)
    monkeypatch.setattr("app.core.embedding_service.generate_text_embedding", _none)


async def _all_docs(session) -> list[FashionKnowledgeDocument]:
    return list((await session.execute(select(FashionKnowledgeDocument))).scalars().all())


@pytest.mark.asyncio
async def test_ensure_seeded_persists_corpus_with_metadata(db_session):
    await fashion_rag_service.ensure_seeded(db_session)
    docs = await _all_docs(db_session)

    expected = len(load_seed_documents())
    assert len(docs) == expected >= 30

    titles = {d.title for d in docs}
    assert "Color Matching Fundamentals" in titles          # migrated
    assert "Natural Fibers Guide (Cotton, Linen, Wool, Silk)" in titles  # fabric
    assert "South Asian Festive & Ethnic Wear Guide" in titles           # regional

    # New filterable metadata must round-trip into the tags JSONB.
    regional = next(d for d in docs if d.title == "South Asian Festive & Ethnic Wear Guide")
    assert regional.tags["region"] == "south asia"
    assert regional.tags["source"] == "curated"
    assert isinstance(regional.tags["tags"], list) and regional.tags["tags"]


@pytest.mark.asyncio
async def test_ensure_seeded_is_idempotent(db_session):
    await fashion_rag_service.ensure_seeded(db_session)
    first = len(await _all_docs(db_session))
    await fashion_rag_service.ensure_seeded(db_session)
    second = len(await _all_docs(db_session))
    assert first == second


async def _seed_outfits(session, *, users: int, outfits_per_user: int) -> None:
    for _ in range(users):
        uid = uuid.uuid4()
        items = [
            ClosetItem(user_id=uid, name="Tee", category="tops", color="white"),
            ClosetItem(user_id=uid, name="Chinos", category="bottoms", color="navy"),
            ClosetItem(user_id=uid, name="Loafers", category="shoes", color="brown"),
        ]
        for it in items:
            session.add(it)
        await session.flush()
        ids = [str(it.id) for it in items]
        for _ in range(outfits_per_user):
            session.add(Outfit(user_id=uid, name="Look", occasion="casual", item_ids=ids))
    await session.flush()


@pytest.mark.asyncio
async def test_refresh_learned_knowledge_end_to_end(db_session):
    await _seed_outfits(db_session, users=3, outfits_per_user=6)  # 18 outfits, 3 users

    written = await mining.refresh_learned_knowledge(db_session)
    assert written == 1

    learned = [d for d in await _all_docs(db_session) if d.category == "learned"]
    assert len(learned) == 1
    doc = learned[0]
    assert doc.tags["source"] == "user_data"
    assert "18" in doc.content  # aggregate outfit count
    assert "3 users" in doc.content
    assert "top+bottom" in doc.content  # natural-ordered most-worn pairing

    # Re-running refreshes in place — must not accumulate a second learned doc.
    again = await mining.refresh_learned_knowledge(db_session)
    assert again == 1
    learned2 = [d for d in await _all_docs(db_session) if d.category == "learned"]
    assert len(learned2) == 1


@pytest.mark.asyncio
async def test_refresh_from_wear_events_and_history(db_session):
    """Cover the worn-together (wear_events) and successful-OutfitHistory branches."""
    for _ in range(3):
        uid = uuid.uuid4()
        items = [
            ClosetItem(user_id=uid, name="Tee", category="tops", color="black"),
            ClosetItem(user_id=uid, name="Jeans", category="bottoms", color="navy"),
            ClosetItem(user_id=uid, name="Sneakers", category="shoes", color="white"),
        ]
        for it in items:
            db_session.add(it)
        await db_session.flush()
        ids = [it.id for it in items]
        # 5 worn-together outfits per user, grouped by a shared outfit_id.
        for _ in range(5):
            oid = uuid.uuid4()
            for iid in ids:
                db_session.add(WearEvent(user_id=uid, item_id=iid, outfit_id=oid, worn_on=date.today()))
        # 1 successful AI recommendation per user (saved => positive signal).
        db_session.add(
            OutfitHistory(user_id=uid, selected_item_ids=[str(i) for i in ids], was_saved=True)
        )
    await db_session.flush()

    written = await mining.refresh_learned_knowledge(db_session)
    assert written == 1
    learned = [d for d in await _all_docs(db_session) if d.category == "learned"]
    assert len(learned) == 1
    # 3 users * (5 worn + 1 saved-history) = 18 outfits.
    assert "18" in learned[0].content


@pytest.mark.asyncio
async def test_refresh_learned_knowledge_insufficient_data(db_session):
    await _seed_outfits(db_session, users=1, outfits_per_user=3)  # below thresholds

    written = await mining.refresh_learned_knowledge(db_session)
    assert written == 0
    learned = [d for d in await _all_docs(db_session) if d.category == "learned"]
    assert learned == []
