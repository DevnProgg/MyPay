import json
from functools import wraps
from flask import request, jsonify
from app.extensions import redis_client


class IdempotencyService:
    """Handle request idempotency using Redis"""

    DEFAULT_TTL = 86400  # 24 hours

    @staticmethod
    def get_key(idempotency_key: str) -> str:
        """Generate Redis key for idempotency"""
        return f'idempotency:{idempotency_key}'

    @staticmethod
    def get_cached_response(idempotency_key: str):
        """Get cached response for idempotency key"""
        key = IdempotencyService.get_key(idempotency_key)
        cached = redis_client.get(key)

        if cached:
            return json.loads(cached)
        return None

    @staticmethod
    def cache_response(idempotency_key: str, response_data: dict, ttl: int = DEFAULT_TTL):
        """Cache response for future idempotent requests"""
        key = IdempotencyService.get_key(idempotency_key)
        redis_client.set(key, json.dumps(response_data), ex=ttl)

    @staticmethod
    def delete_cached_response(idempotency_key: str):
        """Delete cached response"""
        key = IdempotencyService.get_key(idempotency_key)
        redis_client.delete(key)


def idempotent(ttl: int = IdempotencyService.DEFAULT_TTL):
    """Decorator to make endpoints idempotent"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get idempotency key from header
            idempotency_key = request.headers.get('Idempotency-Key')

            if not idempotency_key:
                return jsonify({
                    'error': 'Missing Idempotency-Key header',
                    'message': 'All mutation requests require an Idempotency-Key header'
                }), 400

            # Check for cached response
            cached = IdempotencyService.get_cached_response(idempotency_key)

            if cached:
                # Return cached response with 200 status
                return jsonify(cached), cached.get('_status_code', 200)

            # Execute function
            result = f(*args, **kwargs)

            # Cache successful response
            if isinstance(result, tuple):
                response_data, status_code = result
                if hasattr(response_data, 'get_json'):
                    response_json = response_data.get_json()
                else:
                    response_json = response_data

                response_json['_status_code'] = status_code
                IdempotencyService.cache_response(idempotency_key, response_json, ttl)

            return result

        return decorated_function

    return decorator