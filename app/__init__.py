from flask import Flask
from flask_cors import CORS
from app.extensions import db, migrate, jwt, redis_client, socketio
from app.config import config


def create_app(config_name='development'):
    """Application factory pattern"""
    app = Flask(__name__)

    # Load configuration
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    redis_client.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*")
    CORS(app)

    # Register blueprints
    from app.api import payments_bp, webhooks_bp, admin_bp, health_bp
    app.register_blueprint(payments_bp, url_prefix='/api/v1/payments')
    app.register_blueprint(webhooks_bp, url_prefix='/api/v1/webhooks')
    app.register_blueprint(admin_bp, url_prefix='/api/v1/admin')
    app.register_blueprint(health_bp, url_prefix='/api/v1')

    # Error handlers
    register_error_handlers(app)

    return app


def register_error_handlers(app):
    """Register error handlers"""
    from flask import jsonify

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': 'Bad request', 'message': str(error)}), 400

    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({'error': 'Unauthorized', 'message': str(error)}), 401

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found', 'message': str(error)}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error', 'message': str(error)}), 500