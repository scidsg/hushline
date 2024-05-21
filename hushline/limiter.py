import os
import time

import redis
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

storage_uri = os.getenv("REDIS_URI", "memory://")
if storage_uri.startswith("redis://"):
    # Wait for redis to be available
    r = redis.Redis.from_url(storage_uri, decode_responses=True)
    while True:
        try:
            r.ping()
            print("Successfully connected to redis")
            break
        except redis.exceptions.ConnectionError:
            print("Waiting for Redis...")
            time.sleep(1)

print("Using limiter storage URI:", storage_uri)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=storage_uri,
)
