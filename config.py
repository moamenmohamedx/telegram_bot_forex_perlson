"""
Configuration Loader
====================
Loads secrets from .env and user settings from config.yaml
"""

import os
import yaml
from dotenv import load_dotenv

load_dotenv()


def load_config(config_path: str = 'config.yaml') -> dict:
    """Load configuration from YAML file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


# === Load config.yaml ===
CONFIG = load_config()

# === TELEGRAM (secrets from .env, channels from yaml) ===
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID', 0))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')
TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE', '')
TELEGRAM_CHANNELS = CONFIG.get('channels', [])

# === MT5 (secrets from .env, path from yaml) ===
MT5_LOGIN = int(os.getenv('MT5_LOGIN', 0))
MT5_PASSWORD = os.getenv('MT5_PASSWORD', '')
MT5_SERVER = os.getenv('MT5_SERVER', '')
MT5_PATH = CONFIG.get('mt5_path', 'C:/Program Files/MetaTrader 5/terminal64.exe')

# === TRADING (all from yaml) ===
LOT_SIZE = CONFIG.get('lot_size', 0.01)
MAX_SLIPPAGE = CONFIG.get('max_slippage', 10)
MAGIC_NUMBER = CONFIG.get('magic_number', 234567)
TRADING_ENABLED = CONFIG.get('trading_enabled', False)


def validate_config() -> bool:
    """Check all required values are set"""
    errors = []
    
    # Check secrets (.env)
    if not TELEGRAM_API_ID:
        errors.append("Missing TELEGRAM_API_ID in .env")
    if not TELEGRAM_API_HASH:
        errors.append("Missing TELEGRAM_API_HASH in .env")
    if not TELEGRAM_PHONE:
        errors.append("Missing TELEGRAM_PHONE in .env")
    if not MT5_LOGIN:
        errors.append("Missing MT5_LOGIN in .env")
    if not MT5_PASSWORD:
        errors.append("Missing MT5_PASSWORD in .env")
    if not MT5_SERVER:
        errors.append("Missing MT5_SERVER in .env")
    
    # Check yaml settings
    if not TELEGRAM_CHANNELS:
        errors.append("No channels configured in config.yaml")
    
    if errors:
        for error in errors:
            print(f"❌ {error}")
        return False
    
    return True
