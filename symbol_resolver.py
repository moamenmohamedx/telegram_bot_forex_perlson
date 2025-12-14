"""
Symbol Resolver Module
======================
Universal forex/crypto symbol resolver for mapping aliases to official MT5 symbols.

Supports:
- Precious metals (GOLD, SILVER, PLATINUM, PALLADIUM)
- Major forex pairs (EUR, GBP, JPY, AUD, NZD, CAD, CHF)
- Cryptocurrency (BITCOIN, ETHEREUM, LITECOIN, RIPPLE, etc.)
- Commodities (OIL, CRUDE, GAS)
- Indices (SPX, NASDAQ, DOW, DAX, FTSE, NIKKEI)
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SymbolResolver:
    """
    Universal forex/crypto symbol resolver.
    Maps common names and aliases to official MT5 symbols.
    """
    
    ALIAS_MAP = {
        # === PRECIOUS METALS ===
        'GOLD': 'XAUUSD',
        'XAU': 'XAUUSD',
        'SILVER': 'XAGUSD',
        'XAG': 'XAGUSD',
        'PLATINUM': 'XPTUSD',
        'XPT': 'XPTUSD',
        'PALLADIUM': 'XPDUSD',
        'XPD': 'XPDUSD',
        
        # === MAJOR FOREX PAIRS ===
        'EUR': 'EURUSD',
        'EURO': 'EURUSD',
        'GBP': 'GBPUSD',
        'POUND': 'GBPUSD',
        'CABLE': 'GBPUSD',
        'JPY': 'USDJPY',
        'YEN': 'USDJPY',
        'AUD': 'AUDUSD',
        'AUSSIE': 'AUDUSD',
        'NZD': 'NZDUSD',
        'KIWI': 'NZDUSD',
        'CAD': 'USDCAD',
        'LOONIE': 'USDCAD',
        'CHF': 'USDCHF',
        'SWISSIE': 'USDCHF',
        'FRANC': 'USDCHF',
        
        # === CRYPTOCURRENCY ===
        'BITCOIN': 'BTCUSD',
        'BTC': 'BTCUSD',
        'ETHEREUM': 'ETHUSD',
        'ETH': 'ETHUSD',
        'LITECOIN': 'LTCUSD',
        'LTC': 'LTCUSD',
        'RIPPLE': 'XRPUSD',
        'XRP': 'XRPUSD',
        'CARDANO': 'ADAUSD',
        'ADA': 'ADAUSD',
        'DOGECOIN': 'DOGEUSD',
        'DOGE': 'DOGEUSD',
        'POLKADOT': 'DOTUSD',
        'DOT': 'DOTUSD',
        'SOLANA': 'SOLUSD',
        'SOL': 'SOLUSD',
        
        # === COMMODITIES ===
        'OIL': 'USOIL',
        'CRUDE': 'USOIL',
        'WTI': 'USOIL',
        'BRENT': 'UKOIL',
        'GAS': 'NATGAS',
        'NATURALGAS': 'NATGAS',
        'COPPER': 'COPPER',
        'WHEAT': 'WHEAT',
        'CORN': 'CORN',
        
        # === INDICES ===
        'SPX': 'US500',
        'SP500': 'US500',
        'S&P': 'US500',
        'NASDAQ': 'NAS100',
        'NAS': 'NAS100',
        'DOW': 'US30',
        'DOWJONES': 'US30',
        'DAX': 'GER30',
        'FTSE': 'UK100',
        'NIKKEI': 'JPN225',
        'CAC': 'FRA40',
        'ASX': 'AUS200',
    }
    
    @classmethod
    def resolve(cls, text: str) -> Optional[str]:
        """
        Resolve symbol from text using comprehensive alias map.
        
        Args:
            text: Message text containing symbol or alias
            
        Returns:
            Official MT5 symbol or None
            
        Examples:
            resolve("SELL GOLD NOW") → "XAUUSD"
            resolve("BUY BTC") → "BTCUSD"
            resolve("EUR/USD") → "EURUSD"
        """
        text_upper = text.upper()
        
        # Strategy 1: Try direct 6-7 char symbol match first (XAUUSD, BTCUSD, etc.)
        symbol_pattern = r'\b([A-Z]{6,7})\b'
        matches = re.findall(symbol_pattern, text_upper)
        for match in matches:
            # Check if it's a known official symbol
            if match in cls.get_all_official_symbols():
                logger.debug(f"🎯 Direct symbol match: {match}")
                return match
        
        # Strategy 2: Try alias matching
        for alias, official in cls.ALIAS_MAP.items():
            # Word boundary match to avoid false positives
            if re.search(rf'\b{alias}\b', text_upper):
                logger.info(f"🔍 Resolved alias: '{alias}' → '{official}'")
                return official
        
        return None
    
    @classmethod
    def get_all_official_symbols(cls) -> set:
        """
        Get all official MT5 symbols (values from alias map + additional pairs).
        
        Returns:
            Set of official symbol strings
        """
        official_symbols = set(cls.ALIAS_MAP.values())
        
        # Add forex pairs not in alias map
        official_symbols.update({
            'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD',
            'NZDUSD', 'USDCHF', 'GBPJPY', 'EURJPY', 'AUDJPY',
            'EURGBP', 'EURAUD', 'EURNZD', 'EURCAD', 'EURCHF',
            'GBPAUD', 'GBPNZD', 'GBPCAD', 'GBPCHF',
            'XAUUSD', 'XAGUSD', 'XPTUSD', 'XPDUSD',
            'BTCUSD', 'ETHUSD', 'LTCUSD', 'XRPUSD',
            'USOIL', 'UKOIL', 'NATGAS',
            'US500', 'NAS100', 'US30', 'GER30', 'UK100', 'JPN225',
        })
        
        return official_symbols
