"""
Dramatiq worker infrastructure for async task processing.

This module sets up the Redis broker for Dramatiq workers and provides
shared configuration for all worker modules.
"""
import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.config import settings

# Configure Redis broker for Dramatiq
redis_broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(redis_broker)
