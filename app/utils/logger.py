"""
Logging Configuration
Centralized logging setup for the payment gateway aggregator
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

