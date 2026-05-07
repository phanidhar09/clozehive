"""Kafka producer lifecycle for the API gateway."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.schemas import EventEnvelope

settings = get_settings()
logger = get_logger("events.producer")

_producer = None


async def start() -> None:
    global _producer
    if not settings.kafka_enabled:
        logger.info("kafka_producer_disabled")
        return
    if _producer is not None:
        return

    from aiokafka import AIOKafkaProducer

    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=settings.kafka_client_id,
        request_timeout_ms=settings.kafka_request_timeout_ms,
        acks="all",
        enable_idempotence=True,
    )
    await _producer.start()
    logger.info("kafka_producer_started", bootstrap=settings.kafka_bootstrap_servers)


async def stop() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
        logger.info("kafka_producer_stopped")


async def publish(topic: str, event: EventEnvelope) -> None:
    if not settings.kafka_enabled:
        raise RuntimeError("Kafka producer is disabled")
    global _producer
    if _producer is None:
        await start()
    if _producer is None:
        raise RuntimeError("Kafka producer failed to start")
    await _producer.send_and_wait(topic, key=event.kafka_key(), value=event.kafka_value())
    logger.info(
        "kafka_event_published",
        topic=topic,
        event_id=str(event.event_id),
        request_id=str(event.request_id),
        user_id=str(event.user_id),
    )
