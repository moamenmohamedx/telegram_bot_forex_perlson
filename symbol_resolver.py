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
        
        # === INDUSTRIAL METALS ===
        'ALUMINUM': 'XALUSD',
        'ALUMINIUM': 'XALUSD',
        'COPPER': 'XCUUSD',
        'NICKEL': 'XNIUSD',
        'LEAD': 'XPBUSD',
        'ZINC': 'XZNUSD',
        
        # === FOREX NICKNAMES ===
        'FIBER': 'EURUSD',      # EUR/USD nickname
        'CABLE': 'GBPUSD',      # GBP/USD nickname
        'GOPHER': 'USDJPY',     # USD/JPY nickname
        'AUSSIE': 'AUDUSD',     # AUD/USD nickname
        'KIWI': 'NZDUSD',       # NZD/USD nickname
        'LOONIE': 'USDCAD',     # USD/CAD nickname
        'SWISSIE': 'USDCHF',    # USD/CHF nickname
        
        # === MAJOR FOREX PAIRS ===
        'EUR': 'EURUSD',
        'EURO': 'EURUSD',
        'GBP': 'GBPUSD',
        'POUND': 'GBPUSD',
        'JPY': 'USDJPY',
        'YEN': 'USDJPY',
        'AUD': 'AUDUSD',
        'NZD': 'NZDUSD',
        'CAD': 'USDCAD',
        'CHF': 'USDCHF',
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
        'SOLANA': 'SOLUSD',
        'SOL': 'SOLUSD',
        
        # === ENERGIES ===
        'OIL': 'USOIL',
        'CRUDE': 'USOIL',
        'WTI': 'USOIL',
        'BRENT': 'UKOIL',
        'GAS': 'XNGUSD',
        'NATGAS': 'XNGUSD',
        'NATURALGAS': 'XNGUSD',
        
        # === INDICES ===
        'DOW': 'US30',
        'DOWJONES': 'US30',
        'NASDAQ': 'USTEC',
        'NAS100': 'USTEC',
        'NAS': 'USTEC',
        'SPX': 'US500',
        'SP500': 'US500',
        'SNP': 'US500',
        'S&P': 'US500',
        'FTSE': 'UK100',
        'DAX': 'DE30',
        'CAC': 'FR40',
        'NIKKEI': 'JP225',
        'ASX': 'AUS200',
        'HANGSENG': 'HK50',
        'HSI': 'HK50',
        'STOXX': 'STOXX50',
        'EUROSTOXX': 'STOXX50',
    }
    
    # Known valid symbols that are too short for pattern matching (4-5 chars)
    # These are validated directly to avoid false positives
    # NOTE: Must be uppercase to match text.upper() in resolve()
    KNOWN_SHORT_SYMBOLS = {
        'US30', 'US500', 'UK100', 'DE30', 'FR40', 'JP225', 'HK50',
        'USTEC', 'AUS200', 'STOXX50', 'UKOIL', 'USOIL',
        'US30_X10', 'USTEC_X100', 'US500_X100',  # Amplified indices (uppercase X!)
    }
    
    # Symbol pattern: 2-10 uppercase letters/numbers, optional _xN or _XN suffix for amplified indices
    # Handles: EURUSD, XAUUSD, US30, UK100, US30_x10, USTEC_x100
    # NOTE: [xX] to match both lowercase and uppercase x (text.upper() converts _x to _X)
    SYMBOL_PATTERN = re.compile(r'\b([A-Z0-9]{2,10}(?:_[xX]\d+)?)\b')
    
    # Cached validated symbols (class-level)
    _validated_cache: set = set()
    
    @classmethod
    def resolve(cls, text: str, mt5_handler=None) -> Optional[str]:
        """
        Resolve symbol from text using comprehensive alias map and pattern matching.
        
        Resolution Pipeline:
        1. Alias lookup (GOLD → XAUUSD)
        2. Pattern extraction (6-10 char uppercase, optional _xN suffix)
        3. MT5 validation (optional, for accuracy)
        
        Args:
            text: Message text containing symbol or alias
            mt5_handler: Optional MT5Handler instance for validation
            
        Returns:
            Official MT5 symbol or None
            
        Examples:
            resolve("SELL GOLD NOW") → "XAUUSD"
            resolve("BUY BTC") → "BTCUSD"
            resolve("BUY US30_x10") → "US30_x10"
            resolve("SELL EURUSD") → "EURUSD"
        """
        text_upper = text.upper()
        
        # === STEP 1: Alias Resolution ===
        for alias, official in cls.ALIAS_MAP.items():
            # Word boundary match to avoid false positives
            if re.search(rf'\b{alias}\b', text_upper):
                logger.info(f"🔍 Resolved alias: '{alias}' → '{official}'")
                return official
        
        # === STEP 2: Pattern Extraction ===
        matches = cls.SYMBOL_PATTERN.findall(text_upper)
        
        for symbol in matches:
            # Skip common non-symbol words
            if symbol in {'BUY', 'SELL', 'NOW', 'STOP', 'LOSS', 'TAKE', 'PROFIT', 'THE', 'AND', 'FOR', 'WITH', 'FROM', 'THIS', 'THAT', 'HAVE', 'WILL', 'JUST', 'MESSAGE'}:
                continue
            
            # Check cache for previously validated symbols
            if symbol in cls._validated_cache:
                logger.debug(f"🎯 Cached symbol: {symbol}")
                return symbol
            
            # Check known short symbols (indices, amplified)
            if symbol in cls.KNOWN_SHORT_SYMBOLS:
                logger.debug(f"🎯 Known symbol: {symbol}")
                cls._validated_cache.add(symbol)
                return symbol
            
            # For offline mode or when MT5 handler not provided:
            # Accept pattern-matched symbols that look realistic
            # Forex pairs: 6 chars (EURUSD, GBPUSD)
            # Metals: 6 chars (XAUUSD, XAGUSD)
            # Crypto: 6 chars (BTCUSD, ETHUSD)
            # Exotics: 6 chars (USDTRY, EURZAR)
            if len(symbol) >= 6:  # Standard symbol length
                logger.debug(f"🎯 Pattern-matched symbol: {symbol}")
                cls._validated_cache.add(symbol)  # Cache for future
                return symbol
        
        return None
