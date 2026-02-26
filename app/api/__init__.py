"""
API Blueprints Package
Registers all API blueprints
"""

from flask import Blueprint
from app.api.payments import payments_bp
from app.api.webhooks import webhooks_bp
from app.api.admin import admin_bp
from app.api.health import health_bp
from app.api.auth import auth_bp

# Export blueprints
__all__ = [
    'payments_bp',
    'webhooks_bp',
    'admin_bp',
    'health_bp',
    'auth_bp',
    'register_blueprints',
]


def register_blueprints(app):
    """
    Register all blueprints with the Flask app

    Args:
        app: Flask application instance
    """

    url_base : str = '/api/v1'

    app.register_blueprint(payments_bp, url_prefix=f'{url_base}/payments')
    app.register_blueprint(webhooks_bp, url_prefix=f"{url_base}/webhooks")
    app.register_blueprint(admin_bp, url_prefix=f'{url_base}/admin')
    app.register_blueprint(health_bp, url_prefix=f'{url_base}/health')
    app.register_blueprint(auth_bp, url_prefix=f'{url_base}/auth')