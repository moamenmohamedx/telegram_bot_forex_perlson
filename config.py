"""
Configuration Loader
====================
Single source of truth: .env file

All configuration is loaded from environment variables.
Type conversion is handled explicitly for safety.
"""

import os
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)


# === TYPE CONVERSION HELPERS ===

def _parse_bool(value: str, default: bool = False) -> bool:
    """Parse string to boolean (true/yes/1/on = True)"""
    if value is None:
        return default
    return value.lower().strip() in ('true', 'yes', '1', 'on')


def _parse_int(value: str, default: int) -> int:
    """Parse string to integer with fallback default"""
    if not value:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _parse_float(value: str, default: float) -> float:
    """Parse string to float with fallback default"""
    if not value:
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def _parse_list(value: str, subtype: type = str) -> list:
    """Parse comma-separated string to list with type conversion"""
    if not value:
        return []
    items = [item.strip() for item in value.split(',') if item.strip()]
    if subtype != str:
        items = [subtype(item) for item in items]
    return items


# === TELEGRAM CONFIGURATION ===
TELEGRAM_API_ID = _parse_int(os.getenv('TELEGRAM_API_ID'), 0)
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')
TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE', '')
TELEGRAM_CHANNELS = _parse_list(os.getenv('TELEGRAM_CHANNELS', ''), int)

# === MT5 CONFIGURATION ===
MT5_LOGIN = _parse_int(os.getenv('MT5_LOGIN'), 0)
MT5_PASSWORD = os.getenv('MT5_PASSWORD', '')
MT5_SERVER = os.getenv('MT5_SERVER', '')
MT5_PATH = os.getenv('MT5_PATH', 'C:/Program Files/MetaTrader 5/terminal64.exe')

# === TRADING CONFIGURATION ===
LOT_SIZE = _parse_float(os.getenv('LOT_SIZE'), 0.0)  # Required - no default
TRADING_ENABLED = _parse_bool(os.getenv('TRADING_ENABLED'), False)

# === INTERNAL CONSTANTS (not user-configurable) ===
# Deviation: 20 points is safe default for most forex/CFD pairs
# Magic number: Identifies this bot's trades (non-zero to distinguish from manual)
_DEFAULT_DEVIATION = 20
_MAGIC_NUMBER = 234567


def validate_config() -> bool:
    """
    Validate all required configuration values.
    Returns True if valid, False if errors found.
    """
    errors = []

    # === TELEGRAM VALIDATION ===
    if not TELEGRAM_API_ID:
        errors.append("Missing TELEGRAM_API_ID in .env")
    if not TELEGRAM_API_HASH:
        errors.append("Missing TELEGRAM_API_HASH in .env")
    if not TELEGRAM_PHONE:
        errors.append("Missing TELEGRAM_PHONE in .env")
    if not TELEGRAM_CHANNELS:
        errors.append("Missing TELEGRAM_CHANNELS in .env (format: -123456,-789012)")

    # === MT5 VALIDATION ===
    if not MT5_LOGIN:
        errors.append("Missing MT5_LOGIN in .env")
    if not MT5_PASSWORD:
        errors.append("Missing MT5_PASSWORD in .env")
    if not MT5_SERVER:
        errors.append("Missing MT5_SERVER in .env")

    # === TRADING VALIDATION ===
    if LOT_SIZE <= 0:
        errors.append("Missing or invalid LOT_SIZE in .env (required, e.g., LOT_SIZE=0.5)")

    # Report errors
    if errors:
        for error in errors:
            logger.error(f"❌ {error}")
        return False

    return True
