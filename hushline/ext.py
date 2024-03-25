import os

from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

bcrypt = Bcrypt()

# Check for an environment variable or use in-memory storage as fallback
REDIS_URI = os.getenv("REDIS_URI")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=REDIS_URI,
)
