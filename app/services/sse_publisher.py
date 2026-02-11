"""
SSE Publisher service for real-time diagnosis progress updates.

Uses Redis pub/sub to publish events that are consumed by the SSE endpoint.
"""
import json
import redis
from app.config import settings


class SSEPublisher:
    """Publishes SSE events via Redis pub/sub."""

    def __init__(self):
        self.redis = redis.from_url(settings.redis_url)

    def _get_channel(self, run_id: int) -> str:
        """Get Redis pub/sub channel name for a diagnosis run."""
        return f"diagnosis:{run_id}"

    def _publish(self, run_id: int, event_type: str, data: dict):
        """
        Publish an SSE event to Redis.

        Args:
            run_id: DiagnosisRun ID
            event_type: Event type (progress, result, complete, error)
            data: Event data as dict
        """
        channel = self._get_channel(run_id)
        message = json.dumps({
            "event": event_type,
            "data": data
        })
        self.redis.publish(channel, message)

    def publish_progress(self, run_id: int, completed: int, total: int, ingredient: str):
        """
        Publish progress update event.

        Args:
            run_id: DiagnosisRun ID
            completed: Number of ingredients completed
            total: Total number of ingredients
            ingredient: Name of the ingredient just completed
        """
        self._publish(run_id, "progress", {
            "completed": completed,
            "total": total,
            "ingredient": ingredient
        })

    def publish_result(self, run_id: int, result_dict: dict):
        """
        Publish a completed diagnosis result.

        Args:
            run_id: DiagnosisRun ID
            result_dict: Full DiagnosisResult data
        """
        self._publish(run_id, "result", result_dict)

    def publish_discounted(self, run_id: int, discounted_dict: dict):
        """
        Publish a discounted ingredient (confounder or medically unlikely).

        Args:
            run_id: DiagnosisRun ID
            discounted_dict: DiscountedIngredient data
        """
        self._publish(run_id, "discounted", discounted_dict)

    def publish_complete(self, run_id: int, total_results: int):
        """
        Publish completion event.

        Args:
            run_id: DiagnosisRun ID
            total_results: Total number of results generated
        """
        self._publish(run_id, "complete", {
            "run_id": run_id,
            "total_results": total_results
        })

    def publish_error(self, run_id: int, message: str):
        """
        Publish error event.

        Args:
            run_id: DiagnosisRun ID
            message: Error message
        """
        self._publish(run_id, "error", {
            "message": message
        })

    def close(self):
        """Close Redis connection."""
        self.redis.close()


class SSESubscriber:
    """Subscribes to SSE events from Redis pub/sub."""

    def __init__(self, run_id: int):
        self.run_id = run_id
        self.redis = redis.from_url(settings.redis_url)
        self.pubsub = self.redis.pubsub()
        self.channel = f"diagnosis:{run_id}"
        self.pubsub.subscribe(self.channel)

    async def listen(self):
        """
        Async generator that yields SSE events.

        Yields:
            Tuple of (event_type, data) for each event
        """
        import asyncio

        while True:
            message = self.pubsub.get_message(timeout=1.0)
            if message and message["type"] == "message":
                try:
                    payload = json.loads(message["data"])
                    event_type = payload.get("event", "message")
                    data = payload.get("data", {})
                    yield (event_type, data)

                    # Stop on complete or error
                    if event_type in ("complete", "error"):
                        break
                except json.JSONDecodeError:
                    continue
            else:
                # Small delay to prevent busy-waiting
                await asyncio.sleep(0.1)

    def close(self):
        """Cleanup resources."""
        self.pubsub.unsubscribe(self.channel)
        self.pubsub.close()
        self.redis.close()
