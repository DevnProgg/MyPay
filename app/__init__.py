from flask import Flask
from flask_cors import CORS

from app.api import register_blueprints
from app.extensions import db, jwt, redis_client, celery_app
from app.config import Config
from app.extensions.celery_extention import init_celery


def create_app():
    """Application factory pattern"""
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(Config)
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI

    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    redis_client.init_app(app)
    init_celery(celery_app, app)

    CORS(app)

    # Register blueprints
    register_blueprints(app)

    # Error handlers
    register_error_handlers(app)

    return app

def register_error_handlers(appk):
    from flask import jsonify
    from app.errors.exceptions import AppError

    @appk.errorhandler(AppError)
    def handle_app_error(error):
        return jsonify({
            "error": error.error,
            "message": error.message
        }), error.status_code