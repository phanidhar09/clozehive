"""Kafka consumer worker for asynchronous AI workflows."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.events import topics
from app.events.schemas import EventEnvelope
from app.services import ai_agent_client, db

settings = get_settings()
logger = get_logger("ai_worker")


async def publish(producer: AIOKafkaProducer, topic: str, event: EventEnvelope) -> None:
    await producer.send_and_wait(topic, key=event.key(), value=event.value())
    logger.info("event_published", topic=topic, request_id=str(event.request_id))


async def publish_dead_letter(
    producer: AIOKafkaProducer,
    *,
    source_topic: str,
    event: EventEnvelope,
    error: str,
) -> None:
    dlq = EventEnvelope(
        event_type=topics.DEAD_LETTER,
        request_id=event.request_id,
        user_id=event.user_id,
        payload={
            "source_topic": source_topic,
            "source_event": event.model_dump(mode="json"),
            "error": error,
        },
    )
    await publish(producer, topics.DEAD_LETTER, dlq)


async def handle_event(producer: AIOKafkaProducer, topic: str, event: EventEnvelope) -> None:
    if await db.already_processed(event.event_id):
        logger.info("event_duplicate_ignored", event_id=str(event.event_id), topic=topic)
        return

    await db.mark_processing(event.request_id)

    if topic == topics.IMAGE_UPLOADED:
        result = await ai_agent_client.analyze_image(
            event.payload["file_path"],
            event.payload.get("media_type", "image/jpeg"),
        )
        payload = {
            "upload_id": event.payload.get("upload_id"),
            "analysis": result,
            "name_override": event.payload.get("name_override"),
            "category_override": event.payload.get("category_override"),
        }
        await db.complete_request(event.request_id, payload)
        await publish(
            producer,
            topics.IMAGE_ANALYZED,
            EventEnvelope(
                event_type=topics.IMAGE_ANALYZED,
                request_id=event.request_id,
                user_id=event.user_id,
                payload=payload,
            ),
        )

    elif topic == topics.OUTFIT_REQUESTED:
        result = await ai_agent_client.generate_outfit(event.payload)
        await db.complete_request(event.request_id, result)
        await publish(
            producer,
            topics.OUTFIT_GENERATED,
            EventEnvelope(
                event_type=topics.OUTFIT_GENERATED,
                request_id=event.request_id,
                user_id=event.user_id,
                payload=result,
            ),
        )

    elif topic == topics.TRIP_PLANNED:
        result = await ai_agent_client.generate_packing(event.payload)
        await db.complete_request(event.request_id, result)
        await publish(
            producer,
            topics.PACKING_READY,
            EventEnvelope(
                event_type=topics.PACKING_READY,
                request_id=event.request_id,
                user_id=event.user_id,
                payload=result,
            ),
        )

    elif topic == topics.AI_CHAT_REQUESTED:
        sequence = 0
        async for stream_event in ai_agent_client.stream_chat(event.payload):
            sequence += 1
            await publish(
                producer,
                topics.AI_RESPONSE_STREAM,
                EventEnvelope(
                    event_type=topics.AI_RESPONSE_STREAM,
                    request_id=event.request_id,
                    user_id=event.user_id,
                    payload={"sequence": sequence, **stream_event},
                ),
            )

    await db.record_processed(event.event_id, topic, event.request_id)


async def run() -> None:
    setup_logging()
    logger.info("ai_worker_starting", bootstrap=settings.kafka_bootstrap_servers)

    consumer = AIOKafkaConsumer(
        *topics.COMMAND_TOPICS,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_group_id,
        client_id=settings.kafka_client_id,
        enable_auto_commit=False,
        auto_offset_reset="latest",
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=f"{settings.kafka_client_id}-producer",
        acks="all",
        enable_idempotence=True,
    )

    await consumer.start()
    await producer.start()
    try:
        async for message in consumer:
            topic = message.topic
            try:
                raw: dict[str, Any] = json.loads(message.value.decode("utf-8"))
                event = EventEnvelope(**raw)
                logger.info("event_received", topic=topic, request_id=str(event.request_id))
                await handle_event(producer, topic, event)
                await consumer.commit()
            except Exception as exc:
                logger.error("event_processing_failed", topic=topic, error=str(exc))
                try:
                    if "event" in locals():
                        await db.fail_request(event.request_id, str(exc))
                        await publish_dead_letter(producer, source_topic=topic, event=event, error=str(exc))
                finally:
                    await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()
        await ai_agent_client.close()
        await db.close()
        logger.info("ai_worker_stopped")


if __name__ == "__main__":
    asyncio.run(run())
