"""
PII Sanitizer — removes or masks Personally Identifiable Information (PII) from data.

Responsible for:
  - Masking email addresses
  - Redacting phone numbers  
  - Hiding names and personal details
  - Removing sensitive fields (SSN, credit card, API keys)
  - Sanitizing both payloads and outputs before logging/broadcasting
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)

# ── Patterns for PII detection ────────────────────────────────────────────────

# Email pattern (improved)
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

# Phone pattern (international formats)
PHONE_PATTERN = re.compile(r'(\+?\d{1,3}[-.\s]?)?\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})|\+?\d{10,15}')

# SSN pattern (XXX-XX-XXXX or XXXXXXXXX)
SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}|\b\d{9}\b')

# Credit card pattern (various formats)
CC_PATTERN = re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}|\b\d{4}[\s-]?\d{6}[\s-]?\d{5}\b')

# API key pattern (various formats)
APIKEY_PATTERN = re.compile(r'(api[_-]?key|apikey|token|secret|password|passwd|auth[_-]?key|bearer|jwt)[\s:=]*["\']?([A-Za-z0-9_\-\.]{20,})["\']?', re.IGNORECASE)

# Bank account pattern
BANK_PATTERN = re.compile(r'\b\d{8,17}\b')

# IP address pattern
IP_PATTERN = re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b')

# URL with sensitive parameters
URL_PATTERN = re.compile(r'https?://[^\s]*?(password|token|key|secret)[^\s]*', re.IGNORECASE)

# Name pattern (basic - can be improved with NLP)
NAME_PATTERN = re.compile(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b')

# Address pattern (basic)
ADDRESS_PATTERN = re.compile(r'\b\d+\s+[A-Za-z0-9\s,.-]+\b')

# ── Sensitive field names ─────────────────────────────────────────────────────

SENSITIVE_FIELDS = {
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey", "auth_key",
    "ssn", "social_security", "credit_card", "cc_number", "card_number", "cvv", "cvc",
    "pin", "dob", "date_of_birth", "mother_maiden_name", "license_number", "driver_license",
    "passport", "bank_account", "routing_number", "swift_code", "iban", "account_number",
    "routing", "swift", "iban", "bic", "sort_code", "bsb", "clabe", "aba", "fedwire",
    "email", "phone", "mobile", "telephone", "fax", "cell", "contact", "address",
    "street", "city", "state", "zip", "postal", "country", "ip_address", "mac_address",
    "device_id", "session_id", "user_id", "customer_id", "client_id", "tenant_id",
    "subscription_id", "order_id", "transaction_id", "payment_id", "invoice_id",
    "contract_id", "agreement_id", "license_key", "serial_number", "activation_code",
    "oauth_token", "refresh_token", "access_token", "bearer_token", "jwt_token",
    "private_key", "public_key", "certificate", "csr", "pem", "der", "p12", "pfx",
    "ssh_key", "pgp_key", "gpg_key", "encryption_key", "decryption_key", "signature",
    "hash", "checksum", "digest", "fingerprint", "nonce", "salt", "iv", "vector",
    "seed", "random", "entropy", "uuid", "guid", "correlation_id", "request_id",
    "trace_id", "span_id", "parent_id", "child_id", "root_id", "event_id", "message_id",
}


class PIISanitizer:
    """Utility class for sanitizing PII from data structures."""

    @staticmethod
    def sanitize_email(email: str) -> str:
        """Mask email address: user@domain.com → u***@d***.com"""
        try:
            local, domain = email.split("@")
            if len(local) <= 2:
                masked_local = f"{local[0]}***" if local else "***"
            else:
                masked_local = f"{local[0]}***{local[-1]}"
            domain_parts = domain.split(".")
            if len(domain_parts[0]) <= 2:
                masked_domain = f"{domain_parts[0]}***"
            else:
                masked_domain = f"{domain_parts[0][0]}***{domain_parts[0][-1]}"
            return f"{masked_local}@{masked_domain}.{domain_parts[-1]}"
        except Exception:
            return "***@***.***"

    @staticmethod
    def sanitize_phone(phone: Any) -> str:
        """Mask phone number: (123) 456-7890 → (***) ***-7890"""
        if hasattr(phone, "group"):
            match = phone
        else:
            match = PHONE_PATTERN.search(str(phone))
        if match and match.lastindex and match.lastindex >= 4 and match.group(4):
            return "***-***-" + match.group(4)[-4:]
        return "***-***-****"

    @staticmethod
    def sanitize_ssn(ssn: str) -> str:
        """Mask SSN: 123-45-6789 → ***-**-6789"""
        clean = ssn.replace("-", "")
        if len(clean) >= 4:
            return f"***-**-{clean[-4:]}"
        return "***-**-****"

    @staticmethod
    def sanitize_credit_card(cc: str) -> str:
        """Mask credit card: 1234 5678 9012 3456 → ****-****-****-3456"""
        clean = re.sub(r'\D', '', cc)
        if len(clean) >= 4:
            return f"****-****-****-{clean[-4:]}"
        return "****-****-****-****"

    @staticmethod
    def sanitize_string(value: str) -> str:
        """Sanitize a string value by removing all PII patterns."""
        if not value or not isinstance(value, str):
            return value

        # Replace emails
        value = EMAIL_PATTERN.sub(lambda m: PIISanitizer.sanitize_email(m.group(0)), value)

        # Replace phone numbers
        value = PHONE_PATTERN.sub(PIISanitizer.sanitize_phone, value)

        # Replace SSNs
        value = SSN_PATTERN.sub("***-**-****", value)

        # Replace credit cards
        value = CC_PATTERN.sub("****-****-****-****", value)

        # Replace API keys / tokens (generic)
        value = APIKEY_PATTERN.sub(r"\1: [REDACTED]", value)

        # Replace bank accounts
        value = BANK_PATTERN.sub("****-****-****-****", value)

        # Replace IP addresses
        value = IP_PATTERN.sub("***.***.***.***", value)

        # Replace URLs with sensitive parameters
        value = URL_PATTERN.sub("[REDACTED_URL]", value)

        # Replace potential names (basic masking)
        value = NAME_PATTERN.sub("[NAME]", value)

        # Replace potential addresses
        value = ADDRESS_PATTERN.sub("[ADDRESS]", value)

        return value

    @staticmethod
    def should_sanitize_field(field_name: str) -> bool:
        """Check if a field name suggests it contains sensitive data."""
        field_lower = field_name.lower()
        return any(sensitive in field_lower for sensitive in SENSITIVE_FIELDS)

    @classmethod
    def sanitize_dict(
        cls,
        data: Dict[str, Any],
        recursion_depth: int = 0,
        max_depth: int = 10,
    ) -> Dict[str, Any]:
        """
        Recursively sanitize a dictionary.

        Args:
            data: Input dictionary
            recursion_depth: Current recursion depth
            max_depth: Max recursion depth to prevent infinite loops

        Returns:
            New dictionary with PII sanitized
        """
        if recursion_depth > max_depth:
            return data

        result = {}
        for key, value in data.items():
            is_sensitive = cls.should_sanitize_field(key)

            if is_sensitive:
                if isinstance(value, str):
                    result[key] = "[REDACTED]"
                elif isinstance(value, (int, float)):
                    result[key] = "[REDACTED]"
                else:
                    result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                result[key] = cls.sanitize_dict(value, recursion_depth + 1, max_depth)
            elif isinstance(value, list):
                result[key] = cls.sanitize_list(value, recursion_depth + 1, max_depth)
            elif isinstance(value, str):
                result[key] = cls.sanitize_string(value)
            else:
                result[key] = value

        return result

    @classmethod
    def sanitize_list(
        cls,
        data: List[Any],
        recursion_depth: int = 0,
        max_depth: int = 10,
    ) -> List[Any]:
        """Recursively sanitize a list."""
        if recursion_depth > max_depth:
            return data

        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(cls.sanitize_dict(item, recursion_depth + 1, max_depth))
            elif isinstance(item, list):
                result.append(cls.sanitize_list(item, recursion_depth + 1, max_depth))
            elif isinstance(item, str):
                result.append(cls.sanitize_string(item))
            else:
                result.append(item)

        return result

    @classmethod
    def sanitize_output(cls, data: Any) -> Any:
        """
        Sanitize data for output/logging, removing sensitive fields and masking PII.
        
        This is more aggressive than sanitize() - removes entire sensitive fields.
        """
        if isinstance(data, dict):
            return cls._sanitize_output_dict(data)
        elif isinstance(data, list):
            return [cls.sanitize_output(item) for item in data]
        elif isinstance(data, str):
            return cls.sanitize_string(data)
        else:
            return data

    @classmethod
    def _sanitize_output_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize dictionary for output, removing sensitive fields entirely."""
        result = {}
        for key, value in data.items():
            if cls.should_sanitize_field(key):
                # Remove sensitive fields entirely
                continue
            elif isinstance(value, dict):
                result[key] = cls._sanitize_output_dict(value)
            elif isinstance(value, list):
                result[key] = [cls.sanitize_output(item) for item in data]
            elif isinstance(value, str):
                result[key] = cls.sanitize_string(value)
            else:
                result[key] = value
        return result
        try:
            if isinstance(data, dict):
                return cls.sanitize_dict(data)
            elif isinstance(data, list):
                return cls.sanitize_list(data)
            elif isinstance(data, str):
                return cls.sanitize_string(data)
            else:
                return data
        except Exception as e:
            logger.warning("[PII] Sanitization error: %s", e)
            return data

    @classmethod
    def sanitize(cls, data: Any) -> Any:
        """
        General-purpose sanitizer that chooses the appropriate sanitization method
        based on data type.
        """
        if isinstance(data, dict):
            return cls.sanitize_dict(data)
        elif isinstance(data, list):
            return cls.sanitize_list(data)
        elif isinstance(data, str):
            return cls.sanitize_string(data)
        else:
            return data


# ── Module-level functions ────────────────────────────────────────────────────

def sanitize_payload(payload: Any) -> Any:
    """
    Sanitize an agent input payload.
    Removes/masks all PII before logging or storage.
    """
    return PIISanitizer.sanitize(payload)


def sanitize_output(output: Any) -> Any:
    """
    Sanitize an agent output/result.
    Used before broadcasting via WebSocket or sending to LLM.
    """
    return PIISanitizer.sanitize(output)


def sanitize_for_logging(data: Any) -> str:
    """
    Sanitize data and convert to string for safe logging.
    """
    sanitized = PIISanitizer.sanitize(data)
    try:
        if isinstance(sanitized, (dict, list)):
            return json.dumps(sanitized, default=str)
        else:
            return str(sanitized)
    except Exception:
        return "[UNSERIALIZABLE]"


def mask_email_for_display(email: str) -> str:
    """Mask an email for human-readable display."""
    return PIISanitizer.sanitize_email(email)


def mask_phone_for_display(phone: str) -> str:
    """Mask a phone number for display."""
    return PIISanitizer.sanitize_phone(phone)


# Example usage:
# >>> sanitize_payload({"email": "user@example.com", "ssn": "123-45-6789"})
# {"email": "u***@e***.com", "ssn": "***-**-6789"}

def sanitize_data(data):
    """Sanitize data for safe logging or storage."""
    return PIISanitizer.sanitize(data)
