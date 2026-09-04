"""
Caching service with Redis and in-memory fallback.
Ensures application resilience even when Redis is temporarily unreachable.
"""
import json
import logging
from typing import Any, Optional
import redis

from app.config import settings

logger = logging.getLogger(__name__)


class CacheService:
    """Redis cache manager with graceful fallback."""

    def __init__(self):
        self.redis_client = None
        self._memory_cache = {}
        self._init_redis()

    def _init_redis(self):
        """Attempt to connect to Redis."""
        try:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            # Test connection
            self.redis_client.ping()
            logger.info("✓ Successfully connected to Redis cache")
        except Exception as e:
            logger.warning(f"Redis not available ({e}). Falling back to internal memory cache.")
            self.redis_client = None

    def get(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        if self.redis_client:
            try:
                val = self.redis_client.get(key)
                if val:
                    return json.loads(val)
                return None
            except Exception as e:
                logger.warning(f"Redis get error ({e}), checking in-memory cache")
        return self._memory_cache.get(key)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store item in cache with TTL in seconds."""
        expire = ttl or settings.CACHE_TTL
        if self.redis_client:
            try:
                self.redis_client.setex(key, expire, json.dumps(value, default=str))
                return True
            except Exception as e:
                logger.warning(f"Redis set error ({e}), writing to in-memory cache")
        self._memory_cache[key] = value
        return True

    def delete(self, key: str) -> bool:
        """Remove item from cache."""
        if self.redis_client:
            try:
                self.redis_client.delete(key)
            except Exception:
                pass
        self._memory_cache.pop(key, None)
        return True

    def clear(self):
        """Clear cache."""
        if self.redis_client:
            try:
                self.redis_client.flushdb()
            except Exception:
                pass
        self._memory_cache.clear()


# Create singleton instance
cache = CacheService()
