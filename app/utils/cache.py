import json
import logging
import os
from typing import Any, Optional

import redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)


# =========================================================
# REDIS CONFIGURATION
# =========================================================

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://127.0.0.1:6379/0"
)

REDIS_SOCKET_TIMEOUT = float(
    os.getenv("REDIS_SOCKET_TIMEOUT", "2")
)

REDIS_SOCKET_CONNECT_TIMEOUT = float(
    os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "2")
)


# =========================================================
# REDIS CLIENT
# =========================================================

redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_timeout=REDIS_SOCKET_TIMEOUT,
    socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
    health_check_interval=30,
)


# =========================================================
# REDIS AVAILABILITY
# =========================================================

def redis_available() -> bool:
    """
    Check whether Redis is currently reachable.

    Returns:
        True  -> Redis is available
        False -> Redis is unavailable
    """

    try:
        return bool(redis_client.ping())

    except RedisError as exc:
        logger.warning(
            "Redis unavailable: %s",
            exc
        )

        return False


# =========================================================
# GET
# =========================================================

def cache_get(key: str) -> Optional[Any]:
    """
    Retrieve a value from Redis.

    Returns:
        Deserialized Python value if found.
        None if key does not exist or Redis is unavailable.
    """

    try:
        value = redis_client.get(key)

        if value is None:
            return None

        return json.loads(value)

    except (RedisError, json.JSONDecodeError) as exc:
        logger.warning(
            "Redis cache_get failed for key '%s': %s",
            key,
            exc
        )

        return None


# =========================================================
# SET
# =========================================================

def cache_set(
    key: str,
    value: Any,
    timeout: int = 300
) -> bool:
    """
    Store a Python value in Redis.

    Args:
        key: Redis key.
        value: JSON-serializable Python value.
        timeout: Expiration time in seconds.

    Returns:
        True if successfully cached.
        False otherwise.
    """

    try:
        serialized_value = json.dumps(value)

        redis_client.setex(
            key,
            timeout,
            serialized_value
        )

        return True

    except (RedisError, TypeError, ValueError) as exc:
        logger.warning(
            "Redis cache_set failed for key '%s': %s",
            key,
            exc
        )

        return False


# =========================================================
# DELETE
# =========================================================

def cache_delete(key: str) -> bool:
    """
    Delete one cache key.
    """

    try:
        redis_client.delete(key)
        return True

    except RedisError as exc:
        logger.warning(
            "Redis cache_delete failed for key '%s': %s",
            key,
            exc
        )

        return False


# =========================================================
# DELETE MULTIPLE
# =========================================================

def cache_delete_many(*keys: str) -> bool:
    """
    Delete multiple cache keys.
    """

    if not keys:
        return True

    try:
        redis_client.delete(*keys)
        return True

    except RedisError as exc:
        logger.warning(
            "Redis cache_delete_many failed: %s",
            exc
        )

        return False


# =========================================================
# DELETE BY PATTERN
# =========================================================

def cache_delete_pattern(pattern: str) -> bool:
    """
    Delete Redis keys matching a pattern.

    Example:

        cache_delete_pattern("wheelq:public:cars:*")
    """

    try:
        keys = list(
            redis_client.scan_iter(
                match=pattern
            )
        )

        if keys:
            redis_client.delete(*keys)

        return True

    except RedisError as exc:
        logger.warning(
            "Redis cache_delete_pattern failed for '%s': %s",
            pattern,
            exc
        )

        return False


# =========================================================
# CHECK KEY
# =========================================================

def cache_exists(key: str) -> bool:
    """
    Check whether a cache key exists.
    """

    try:
        return bool(
            redis_client.exists(key)
        )

    except RedisError as exc:
        logger.warning(
            "Redis cache_exists failed for key '%s': %s",
            key,
            exc
        )

        return False


# =========================================================
# GET TTL
# =========================================================

def cache_ttl(key: str) -> int:
    """
    Return remaining TTL.

    -1 = key exists but has no expiration
    -2 = key does not exist
    """

    try:
        return int(
            redis_client.ttl(key)
        )

    except RedisError as exc:
        logger.warning(
            "Redis cache_ttl failed for key '%s': %s",
            key,
            exc
        )

        return -2


# =========================================================
# CLEAR ALL WHEELQ CACHE
# =========================================================

def clear_wheelq_cache() -> bool:
    """
    Delete all WheelQ cache keys.

    Only keys using the wheelq: namespace are affected.
    """

    return cache_delete_pattern(
        "wheelq:*"
    )


def invalidate_admin_dashboard():
    """
    Invalidate cached admin dashboard statistics.
    """
    return cache_delete(
        "wheelq:admin:dashboard:stats"
    )
