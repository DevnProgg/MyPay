from functools import wraps

from flask import request

from app.errors import Unauthorized


from functools import wraps
from flask import request, g
from werkzeug.exceptions import Unauthorized

from app.models import Account


def api_key_required():
    """Validate merchant API key"""

    def decorator(func):
        @wraps(func)
        def decorated_function(*args, **kwargs):
            api_key = request.headers.get("X-API-Key")

            if not api_key:
                raise Unauthorized("API key missing")

            merchant_key = Account.query.filter_by(_api_key=api_key).first()

            if not merchant_key:
                raise Unauthorized("Invalid API key")

            return func(*args, **kwargs)

        return decorated_function

    return decorator