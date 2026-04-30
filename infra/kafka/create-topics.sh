#!/bin/sh
set -eu

BROKERS="${KAFKA_BROKERS:-redpanda:9092}"
PARTITIONS="${KAFKA_PARTITIONS:-6}"
REPLICAS="${KAFKA_REPLICATION_FACTOR:-1}"
RETENTION_MS="${KAFKA_RETENTION_MS:-604800000}"

topics="
image_uploaded
image_analyzed
outfit_requested
outfit_generated
trip_planned
packing_ready
ai_chat_requested
ai_response_stream
dead_letter
"

for topic in $topics; do
  rpk topic create "$topic" \
    --brokers "$BROKERS" \
    --partitions "$PARTITIONS" \
    --replicas "$REPLICAS" \
    --topic-config "retention.ms=$RETENTION_MS" \
    --topic-config "cleanup.policy=delete" || true
done
