"""Kafka result listener that bridges durable events to Redis/WebSocket fanout."""

from __future__ import annotations

from typing import Optional

import asyncio
import json

from app.core.config import get_settings
from app.core.logging import get_logger
from app.events import topics
from app.services import cache_service

settings = get_settings()
logger = get_logger("events.result_listener")

_task: asyncio.Task | None = None
_consumer = None


async def start() -> None:
    global _task
    if not settings.kafka_enabled:
        logger.info("kafka_result_listener_disabled")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_consume_results())


async def stop() -> None:
    global _task, _consumer
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    if _consumer is not None:
        await _consumer.stop()
        _consumer = None


async def _consume_results() -> None:
    global _consumer
    from aiokafka import AIOKafkaConsumer

    while True:
        try:
            _consumer = AIOKafkaConsumer(
                *topics.RESULT_TOPICS,
                bootstrap_servers=settings.kafka_bootstrap_servers,
                group_id=settings.kafka_result_group_id,
                client_id=f"{settings.kafka_client_id}-result-listener",
                enable_auto_commit=False,
                auto_offset_reset="latest",
            )
            await _consumer.start()
            logger.info("kafka_result_listener_started", topics=list(topics.RESULT_TOPICS))

            async for message in _consumer:
                try:
                    event = json.loads(message.value.decode("utf-8"))
                    user_id = event.get("user_id")
                    payload = {
                        "type": "event",
                        "event_type": event.get("event_type"),
                        "request_id": event.get("request_id"),
                        "payload": event.get("payload", {}),
                    }
                    if user_id:
                        client = await cache_service.get_redis()
                        await client.publish(
                            cache_service.websocket_user_channel(str(user_id)),
                            json.dumps({"user_id": user_id, "data": payload}, default=str),
                        )
                    await _consumer.commit()
                except Exception as exc:
                    logger.error("kafka_result_dispatch_failed", error=str(exc))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("kafka_result_listener_error", error=str(exc))
            await asyncio.sleep(5)
