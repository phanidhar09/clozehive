"""Kafka topic constants for the ai-worker service."""

INPUT_TOPICS = [
    "ai.chat.requested",
    "ai.outfit.requested",
    "ai.trip.planned",
    "ai.image.uploaded",
]

RESULT_TOPIC = "ai.results"
DEAD_LETTER_TOPIC = "ai.dead.letter"

# Maps input event_type → result event_type published on RESULT_TOPIC
RESULT_EVENT_TYPE = {
    "ai_chat_requested": "ai_response",
    "outfit_requested": "outfit_generated",
    "trip_planned": "packing_ready",
    "image_uploaded": "image_analyzed",
}
