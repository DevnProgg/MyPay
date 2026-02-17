"""
Custom Decorators
Rate limiting, authentication, and other decorators
"""

from functools import wraps
from flask import request, jsonify, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt
import time
from app.extensions import redis_client


def rate_limit(max_requests=100, window_seconds=60, key_prefix='rate_limit'):
    """
    Rate limiting decorator

    Args:
        max_requests: Maximum number of requests allowed
        window_seconds: Time window in seconds
        key_prefix: Redis key prefix

    Usage:
        @rate_limit(max_requests=10, window_seconds=60)
        def my_endpoint():
            return "Success"
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get client identifier (IP address or user ID)
            if request.headers.get('X-Forwarded-For'):
                client_id = request.headers.get('X-Forwarded-For').split(',')[0]
            else:
                client_id = request.remote_addr

            # Try to get user ID from JWT if available
            try:
                verify_jwt_in_request(optional=True)
                jwt_data = get_jwt()
                if jwt_data:
                    client_id = jwt_data.get('sub', client_id)
            except:
                pass

            # Create Redis key
            current_window = int(time.time() / window_seconds)
            key = f'{key_prefix}:{client_id}:{current_window}'

            # Get current count
            try:
                count = redis_client.get(key)
                if count is None:
                    count = 0
                else:
                    count = int(count)

                # Check if limit exceeded
                if count >= max_requests:
                    return jsonify({
                        'error': 'Rate limit exceeded',
                        'message': f'Maximum {max_requests} requests per {window_seconds} seconds',
                        'retry_after': window_seconds
                    }), 429

                # Increment counter
                redis_client.set(key, count + 1, ex=window_seconds)

            except Exception as e:
                # If Redis fails, allow the request (fail open)
                current_app.logger.warning(f'Rate limit check failed: {str(e)}')

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def require_api_key(f):
    """
    Require API key in header

    Usage:
        @require_api_key
        def my_endpoint():
            return "Success"
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')

        if not api_key:
            return jsonify({
                'error': 'Missing API key',
                'message': 'X-API-Key header is required'
            }), 401

        # Validate API key (you should implement your own validation logic)
        valid_api_keys = current_app.config.get('VALID_API_KEYS', [])

        if api_key not in valid_api_keys:
            return jsonify({
                'error': 'Invalid API key',
                'message': 'The provided API key is not valid'
            }), 401

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """
    Require admin role in JWT

    Usage:
        @jwt_required()
        @admin_required
        def my_endpoint():
            return "Success"
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()

        if not claims.get('is_admin', False):
            return jsonify({
                'error': 'Admin access required',
                'message': 'This endpoint requires admin privileges'
            }), 403

        return f(*args, **kwargs)

    return decorated_function


def log_execution_time(f):
    """
    Log execution time of a function

    Usage:
        @log_execution_time
        def my_function():
            return "Success"
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.utils.logger import get_logger
        logger = get_logger(__name__)

        start_time = time.time()
        result = f(*args, **kwargs)
        end_time = time.time()

        execution_time = end_time - start_time
        logger.info(f'{f.__name__} executed in {execution_time:.4f} seconds')

        return result

    return decorated_function


def cache_response(ttl=300, key_prefix='cache'):
    """
    Cache response in Redis

    Args:
        ttl: Time to live in seconds
        key_prefix: Redis key prefix

    Usage:
        @cache_response(ttl=600)
        def my_endpoint():
            return {"data": "expensive computation"}
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Create cache key from request path and args
            cache_key = f'{key_prefix}:{request.path}:{str(request.args)}'

            try:
                # Try to get cached response
                cached = redis_client.get(cache_key)
                if cached:
                    import json
                    return json.loads(cached)
            except Exception as e:
                current_app.logger.warning(f'Cache retrieval failed: {str(e)}')

            # Execute function
            result = f(*args, **kwargs)

            # Cache the result
            try:
                import json
                redis_client.set(cache_key, json.dumps(result), ex=ttl)
            except Exception as e:
                current_app.logger.warning(f'Cache storage failed: {str(e)}')

            return result

        return decorated_function

    return decorator


def validate_content_type(content_type='application/json'):
    """
    Validate request content type

    Usage:
        @validate_content_type('application/json')
        def my_endpoint():
            return "Success"
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.content_type != content_type:
                return jsonify({
                    'error': 'Invalid content type',
                    'message': f'Content-Type must be {content_type}'
                }), 415

            return f(*args, **kwargs)

        return decorated_function

    return decorator