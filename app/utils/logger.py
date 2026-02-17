"""
Logging Configuration
Centralized logging setup for the payment gateway
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
import os


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # File handler (if logs directory exists)
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except:
                pass

        if os.path.exists(log_dir):
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, 'payment-gateway.log'),
                maxBytes=10485760,  # 10MB
                backupCount=10
            )
            file_handler.setLevel(logging.INFO)

            # File formatter
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

        # Console formatter
        console_formatter = logging.Formatter(
            '%(levelname)s - %(name)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)

        logger.addHandler(console_handler)

    return logger


def configure_app_logging(app):
    """
    Configure logging for the Flask application

    Args:
        app: Flask application instance
    """
    # Set Flask logger level
    app.logger.setLevel(logging.INFO)

    # Add handlers
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except:
            pass

    if os.path.exists(log_dir):
        # Access log
        access_handler = RotatingFileHandler(
            os.path.join(log_dir, 'access.log'),
            maxBytes=10485760,
            backupCount=10
        )
        access_handler.setLevel(logging.INFO)
        access_formatter = logging.Formatter(
            '%(asctime)s - %(remote_addr)s - %(method)s %(path)s - %(status)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        access_handler.setFormatter(access_formatter)

        # Error log
        error_handler = RotatingFileHandler(
            os.path.join(log_dir, 'error.log'),
            maxBytes=10485760,
            backupCount=10
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n%(pathname)s:%(lineno)d',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(error_formatter)

        app.logger.addHandler(error_handler)


class RequestLogger:
    """Middleware to log all requests"""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize request logging"""

        @app.before_request
        def log_request():
            from flask import request
            logger = get_logger('request')
            logger.info(
                f'{request.method} {request.path} - '
                f'IP: {request.remote_addr} - '
                f'User-Agent: {request.headers.get("User-Agent", "Unknown")}'
            )

        @app.after_request
        def log_response(response):
            from flask import request
            logger = get_logger('response')
            logger.info(
                f'{request.method} {request.path} - '
                f'Status: {response.status_code} - '
                f'IP: {request.remote_addr}'
            )
            return response