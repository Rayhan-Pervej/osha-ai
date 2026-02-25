from functools import wraps
from flask import request
import redis
from src.config import settings
from src.api.schemas.responses import error

_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

def rate_limit(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key", "unknows")
        redis_key = f"rate:{api_key}"

        count = _redis.incr(redis_key)

        if count == 1:
            _redis.expire(redis_key, settings.REDIS_RATE_LIMIT_WINDOW_SECONDS)

        if count > settings.REDIS_RATE_LIMIT_REQUESTS:
            return error("rate_limit_exceeded", "Too many requrest. Try again later.", 429)
        
        return f(*args, **kwargs)
    return decorated