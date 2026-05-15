# pyrefly: ignore [missing-import]
import redis
import logging
import json
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize a global Redis connection pool to avoid reconnecting constantly
try:
    redis_pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    redis_client = redis.Redis(connection_pool=redis_pool)
except Exception as e:
    logger.error(f"Failed to initialize Redis pool: {e}")
    redis_client = None

def emit_event(stream_name: str, payload: dict):
    """
    Emit an event to a Redis Stream.
    """
    if not redis_client:
        logger.error("Redis client is not initialized. Cannot emit event.")
        return False
        
    try:
        # Convert all values to string to be stored in Redis stream
        str_payload = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in payload.items()}
        
        msg_id = redis_client.xadd(name=stream_name, fields=str_payload)
        logger.info(f"Successfully emitted event to {stream_name} with msg_id: {msg_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to emit event to {stream_name}: {e}", exc_info=True)
        return False
