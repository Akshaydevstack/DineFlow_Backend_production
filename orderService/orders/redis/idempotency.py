from django.core.cache import cache


IDEMPOTENCY_TTL = 600  # 10 minutes


def get_idempotency_key(user_id, key):
    return f"order:idempotency:{user_id}:{key}"


def get_existing_order(user_id, key):
    redis_key = get_idempotency_key(user_id, key)
    return cache.get(redis_key)


def store_idempotency_key(user_id, key, order_id):
    redis_key = get_idempotency_key(user_id, key)
    cache.set(redis_key, order_id, timeout=IDEMPOTENCY_TTL)