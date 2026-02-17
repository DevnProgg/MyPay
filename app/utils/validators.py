"""
Custom Validators
Validation functions for common data types
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional


def validate_phone_number(phone: str, country_code: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """
    Validate phone number format

    Args:
        phone: Phone number to validate
        country_code: Optional country code (e.g., 'KE' for Kenya)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not phone:
        return False, "Phone number is required"

    # Remove spaces and special characters
    phone_clean = re.sub(r'[\s\-\(\)]', '', phone)

    # Check if phone contains only digits and optional leading +
    if not re.match(r'^\+?\d+$', phone_clean):
        return False, "Phone number must contain only digits and optional leading +"

    # Remove leading +
    phone_digits = phone_clean.lstrip('+')

    # Country-specific validation
    if country_code == 'KE':  # Kenya
        # Kenya numbers: +254XXXXXXXXX or 254XXXXXXXXX or 0XXXXXXXXX
        if phone_digits.startswith('254'):
            if len(phone_digits) != 12:
                return False, "Kenyan phone number with country code should be 12 digits (254XXXXXXXXX)"
        elif phone_digits.startswith('0'):
            if len(phone_digits) != 10:
                return False, "Kenyan phone number should be 10 digits (0XXXXXXXXX)"
        else:
            return False, "Kenyan phone number should start with 254 or 0"

    elif country_code == 'US':  # United States
        # US numbers: +1XXXXXXXXXX or 1XXXXXXXXXX
        if not phone_digits.startswith('1'):
            return False, "US phone number should start with 1"
        if len(phone_digits) != 11:
            return False, "US phone number should be 11 digits (1XXXXXXXXXX)"

    else:
        # Generic validation: between 7 and 15 digits
        if len(phone_digits) < 7 or len(phone_digits) > 15:
            return False, "Phone number should be between 7 and 15 digits"

    return True, None


def validate_amount(amount: any, min_amount: float = 0.01, max_amount: float = 1000000.00) -> tuple[
    bool, Optional[str]]:
    """
    Validate payment amount

    Args:
        amount: Amount to validate
        min_amount: Minimum allowed amount
        max_amount: Maximum allowed amount

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Convert to Decimal for precise comparison
        if isinstance(amount, str):
            amount_decimal = Decimal(amount)
        elif isinstance(amount, (int, float)):
            amount_decimal = Decimal(str(amount))
        elif isinstance(amount, Decimal):
            amount_decimal = amount
        else:
            return False, f"Amount must be a number, got {type(amount).__name__}"

        # Check if positive
        if amount_decimal <= 0:
            return False, "Amount must be greater than 0"

        # Check minimum
        if amount_decimal < Decimal(str(min_amount)):
            return False, f"Amount must be at least {min_amount}"

        # Check maximum
        if amount_decimal > Decimal(str(max_amount)):
            return False, f"Amount must not exceed {max_amount}"

        # Check decimal places (max 2)
        if amount_decimal.as_tuple().exponent < -2:
            return False, "Amount can have at most 2 decimal places"

        return True, None

    except (InvalidOperation, ValueError) as e:
        return False, f"Invalid amount format: {str(e)}"


def validate_currency(currency: str, allowed_currencies: Optional[list] = None) -> tuple[bool, Optional[str]]:
    """
    Validate currency code

    Args:
        currency: Currency code to validate (e.g., 'USD', 'KES')
        allowed_currencies: List of allowed currency codes

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not currency:
        return False, "Currency is required"

    # Check format (3 uppercase letters)
    if not re.match(r'^[A-Z]{3}$', currency):
        return False, "Currency must be a 3-letter uppercase code (e.g., USD, KES, EUR)"

    # Check against allowed currencies if provided
    if allowed_currencies:
        if currency not in allowed_currencies:
            return False, f"Currency must be one of: {', '.join(allowed_currencies)}"

    # Common currency codes
    common_currencies = [
        'USD', 'EUR', 'GBP', 'KES', 'TZS', 'UGX', 'NGN', 'ZAR',
        'JPY', 'CNY', 'INR', 'AUD', 'CAD', 'CHF', 'SEK', 'NZD'
    ]

    if currency not in common_currencies:
        # Warning, but not an error
        pass

    return True, None


def validate_email(email: str) -> tuple[bool, Optional[str]]:
    """
    Validate email address format

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email:
        return False, "Email is required"

    # Basic email regex pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(email_pattern, email):
        return False, "Invalid email format"

    # Check length
    if len(email) > 254:  # RFC 5321
        return False, "Email address is too long (max 254 characters)"

    # Check local part (before @)
    local_part = email.split('@')[0]
    if len(local_part) > 64:  # RFC 5321
        return False, "Email local part is too long (max 64 characters)"

    return True, None


def validate_idempotency_key(key: str) -> tuple[bool, Optional[str]]:
    """
    Validate idempotency key format

    Args:
        key: Idempotency key to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not key:
        return False, "Idempotency key is required"

    # Check length (reasonable range)
    if len(key) < 10 or len(key) > 255:
        return False, "Idempotency key must be between 10 and 255 characters"

    # Check format (alphanumeric, hyphens, underscores)
    if not re.match(r'^[a-zA-Z0-9_-]+$', key):
        return False, "Idempotency key must contain only alphanumeric characters, hyphens, and underscores"

    return True, None


def validate_provider_name(provider: str, available_providers: list) -> tuple[bool, Optional[str]]:
    """
    Validate payment provider name

    Args:
        provider: Provider name to validate
        available_providers: List of available provider names

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not provider:
        return False, "Provider is required"

    if provider.lower() not in [p.lower() for p in available_providers]:
        return False, f"Invalid provider. Available providers: {', '.join(available_providers)}"

    return True, None


def validate_transaction_status(status: str) -> tuple[bool, Optional[str]]:
    """
    Validate transaction status

    Args:
        status: Status to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    valid_statuses = ['pending', 'processing', 'completed', 'failed', 'refunded']

    if status not in valid_statuses:
        return False, f"Invalid status. Must be one of: {', '.join(valid_statuses)}"

    return True, None


def validate_metadata(metadata: dict, max_size: int = 10240) -> tuple[bool, Optional[str]]:
    """
    Validate metadata dictionary

    Args:
        metadata: Metadata dictionary to validate
        max_size: Maximum size in bytes (default 10KB)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if metadata is None:
        return True, None

    if not isinstance(metadata, dict):
        return False, "Metadata must be a dictionary"

    # Check size
    try:
        import json
        metadata_json = json.dumps(metadata)
        if len(metadata_json.encode('utf-8')) > max_size:
            return False, f"Metadata exceeds maximum size of {max_size} bytes"
    except (TypeError, ValueError) as e:
        return False, f"Metadata must be JSON serializable: {str(e)}"

    # Check for reserved keys
    reserved_keys = ['_internal', '_system', '_reserved']
    for key in metadata.keys():
        if key.startswith('_'):
            return False, f"Metadata keys cannot start with underscore (reserved): {key}"

    return True, None


def sanitize_phone_number(phone: str, country_code: Optional[str] = None) -> str:
    """
    Sanitize and format phone number

    Args:
        phone: Phone number to sanitize
        country_code: Optional country code for formatting

    Returns:
        Sanitized phone number
    """
    # Remove all non-digit characters except +
    phone_clean = re.sub(r'[^\d+]', '', phone)

    # Country-specific formatting
    if country_code == 'KE':
        # Convert to 254XXXXXXXXX format
        if phone_clean.startswith('0'):
            phone_clean = '254' + phone_clean[1:]
        elif phone_clean.startswith('+254'):
            phone_clean = phone_clean[1:]
        elif not phone_clean.startswith('254'):
            phone_clean = '254' + phone_clean

    return phone_clean