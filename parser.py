"""
Signal Parser Module
====================
Parses trading signals from Mrbluemax Forex Academy Telegram messages.

Signal Formats Supported:
-------------------------
BUY:  "Buy XAUUSD .. Gold now !" + "Stop loss : 4014.427" + "Take profit : 4055.964"
SELL: "Sell XAUUSD .. Gold now ⬇️" + "Stop loss :4046.138" + "Take Profit:4029.901"
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

from symbol_resolver import SymbolResolver

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Parsed trading signal data"""
    action: Optional[str]              # BUY, SELL, or None
    symbol: Optional[str]              # e.g., XAUUSD, or None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # NEW: Limit order support fields
    order_type: Optional[str] = "MARKET"  # "MARKET" or "LIMIT"
    entry_price: Optional[float] = None   # Required for LIMIT orders
    
    # Multi-message support fields
    is_complete: bool = False          # True if has action+symbol+SL/TP
    signal_type: str = 'UNKNOWN'       # COMPLETE, ENTRY_ONLY, PARAMS_ONLY, INVALID
    
    def __post_init__(self):
        """Validate signal data after initialization."""
        # Validate limit order requirements
        if self.order_type == "LIMIT" and self.entry_price is None:
            raise ValueError("LIMIT order requires entry_price")
        
        # Validate SL/TP positioning for limit orders
        if self.order_type == "LIMIT" and self.entry_price is not None:
            if self.action == "BUY":
                # BUY LIMIT: SL < Entry < TP
                if self.stop_loss is not None and self.stop_loss >= self.entry_price:
                    raise ValueError(f"BUY LIMIT: SL ({self.stop_loss}) must be < Entry ({self.entry_price})")
                if self.take_profit is not None and self.take_profit <= self.entry_price:
                    raise ValueError(f"BUY LIMIT: TP ({self.take_profit}) must be > Entry ({self.entry_price})")
            
            elif self.action == "SELL":
                # SELL LIMIT: TP < Entry < SL
                if self.stop_loss is not None and self.stop_loss <= self.entry_price:
                    raise ValueError(f"SELL LIMIT: SL ({self.stop_loss}) must be > Entry ({self.entry_price})")
                if self.take_profit is not None and self.take_profit >= self.entry_price:
                    raise ValueError(f"SELL LIMIT: TP ({self.take_profit}) must be < Entry ({self.entry_price})")
    
    def __str__(self) -> str:
        """Human-readable representation"""
        if self.signal_type == 'COMPLETE':
            if self.order_type == "LIMIT":
                return f"{self.action} {self.symbol} LIMIT @ {self.entry_price} | SL: {self.stop_loss} | TP: {self.take_profit}"
            return f"{self.action} {self.symbol} | SL: {self.stop_loss} | TP: {self.take_profit}"
        elif self.signal_type == 'ENTRY_ONLY':
            if self.order_type == "LIMIT":
                return f"{self.action} {self.symbol} LIMIT @ {self.entry_price} (no SL/TP)"
            return f"{self.action} {self.symbol} (no SL/TP)"
        elif self.signal_type == 'PARAMS_ONLY':
            return f"SL: {self.stop_loss} | TP: {self.take_profit}"
        return "INVALID"


class SignalParser:
    """Parser for Mrbluemax Forex Academy trading signals"""
    
    def __init__(self):
        # No hardcoded symbols needed - SymbolResolver handles all symbol detection
        pass
    
    def parse(self, message_text: str) -> Optional[Signal]:
        """
        Parse trading signal from Telegram message.
        
        Returns Signal if valid signal found, None otherwise.
        """
        if not message_text:
            return None
        
        try:
            # === STEP 1: Clean and normalize text ===
            text = self._normalize_text(message_text)
            
            # === STEP 2: Detect action type (BUY/SELL/LONG/SHORT) ===
            action = self._extract_action(text)
            
            # === STEP 3: Extract symbol ===
            symbol = self._extract_symbol(text)
            
            # === STEP 4: Detect order type (MARKET/LIMIT) ===
            order_type = self._extract_order_type(text)
            
            # === STEP 5: Extract entry price (for LIMIT orders) ===
            entry_price = self._extract_entry_price(text)
            
            # If entry price found but order_type is MARKET, switch to LIMIT
            if entry_price is not None and order_type == 'MARKET':
                # Check if there's an explicit MARKET keyword
                if 'MARKET' not in text and 'NOW' not in text:
                    order_type = 'LIMIT'
            
            # === STEP 6: Extract Stop Loss and Take Profit ===
            stop_loss = self._extract_price(text, 'SL')
            take_profit = self._extract_price(text, 'TP')
            
            # Log warnings for incomplete signals
            if action and symbol and not stop_loss and not take_profit:
                logger.warning(f"No stop loss found for {action} {symbol}")
            
            # === STEP 7: Create signal object ===
            try:
                signal = Signal(
                    action=action,
                    symbol=symbol,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    order_type=order_type,
                    entry_price=entry_price
                )
            except ValueError as e:
                # Validation error from __post_init__ (e.g., invalid SL/TP for LIMIT)
                logger.warning(f"⚠️ Signal validation failed: {e}")
                return None
            
            # === STEP 8: Classify signal completeness ===
            signal.signal_type = self.classify_signal(signal)
            
            # === STEP 9: Validate and return ===
            if signal.signal_type == 'INVALID':
                logger.debug(f"Invalid signal - missing critical fields")
                return None
            
            # Log parsed signal
            if signal.signal_type == 'COMPLETE':
                logger.info(f"📍 Parsed COMPLETE: {signal}")
            elif signal.signal_type == 'ENTRY_ONLY':
                logger.info(f"📍 Parsed ENTRY_ONLY: {signal}")
            elif signal.signal_type == 'PARAMS_ONLY':
                logger.info(f"📍 Parsed PARAMS_ONLY: {signal}")
            
            return signal
            
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            return None
    
    def classify_signal(self, signal: Signal) -> str:
        """
        Classify signal completeness and update signal metadata.
        
        Returns:
            'COMPLETE', 'ENTRY_ONLY', 'PARAMS_ONLY', or 'INVALID'
        
        Logic:
            COMPLETE     = has action + symbol + (SL or TP)
            ENTRY_ONLY   = has action + symbol, missing SL/TP
            PARAMS_ONLY  = has SL/TP, missing action + symbol
            INVALID      = missing critical fields
        """
        has_entry = (signal.action is not None and signal.symbol is not None)
        has_params = (signal.stop_loss is not None or signal.take_profit is not None)
        
        if has_entry and has_params:
            signal.is_complete = True
            return 'COMPLETE'
        elif has_entry and not has_params:
            signal.is_complete = False
            return 'ENTRY_ONLY'
        elif not has_entry and has_params:
            signal.is_complete = False
            return 'PARAMS_ONLY'
        else:
            return 'INVALID'
    
    def _normalize_text(self, text: str) -> str:
        """Normalize message text for consistent parsing"""
        # Convert to uppercase for consistent matching
        normalized = text.upper()
        
        # Normalize spaced symbols: "xau usd" → "XAUUSD", "EUR USD" → "EURUSD"
        # Use specific patterns to avoid matching BUY/SELL with currency codes
        # Metals: XAU USD, XAG USD
        normalized = re.sub(r'\b(XAU)\s+(USD)\b', r'\1\2', normalized)
        normalized = re.sub(r'\b(XAG)\s+(USD)\b', r'\1\2', normalized)
        # Major currencies: EUR USD, GBP USD, USD JPY, etc.
        normalized = re.sub(r'\b(EUR)\s+(USD)\b', r'\1\2', normalized)
        normalized = re.sub(r'\b(GBP)\s+(USD)\b', r'\1\2', normalized)
        normalized = re.sub(r'\b(USD)\s+(JPY)\b', r'\1\2', normalized)
        normalized = re.sub(r'\b(AUD)\s+(USD)\b', r'\1\2', normalized)
        normalized = re.sub(r'\b(NZD)\s+(USD)\b', r'\1\2', normalized)
        normalized = re.sub(r'\b(USD)\s+(CAD)\b', r'\1\2', normalized)
        normalized = re.sub(r'\b(USD)\s+(CHF)\b', r'\1\2', normalized)
        
        # Standardize common variations
        replacements = {
            'STOP LOSS': 'SL',
            'STOPLOSS': 'SL',
            'STOP-LOSS': 'SL',
            'TAKE PROFIT': 'TP',
            'TAKEPROFIT': 'TP',
            'TAKE-PROFIT': 'TP',
            'TARGET': 'TP',
            '..GOLD': '',      # Remove Gold suffix (e.g., "XAUUSD..Gold")
            '.. GOLD': '',     # Remove Gold suffix with space (e.g., "XAUUSD .. Gold")
            # Note: Don't remove 'GOLD NOW' - it could be the symbol itself!
            # We'll let SymbolResolver handle GOLD → XAUUSD conversion
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    def _extract_action(self, text: str) -> Optional[str]:
        """
        Extract trading action from normalized text.
        
        Supports:
        - BUY, SELL (standard)
        - LONG → BUY, SHORT → SELL (normalized)
        """
        # Check for BUY or LONG
        if re.search(r'\bBUY\b', text):
            return 'BUY'
        if re.search(r'\bLONG\b', text):
            return 'BUY'  # LONG → BUY normalization
        
        # Check for SELL or SHORT
        if re.search(r'\bSELL\b', text):
            return 'SELL'
        if re.search(r'\bSHORT\b', text):
            return 'SELL'  # SHORT → SELL normalization
        
        return None
    
    def _extract_order_type(self, text: str) -> str:
        """
        Detect LIMIT vs MARKET order type from signal text.
        
        Returns:
            'LIMIT' or 'MARKET'
        """
        # Check for explicit MARKET keywords first
        market_keywords = ['MARKET', 'NOW', 'IMMEDIATE', 'ASAP']
        if any(keyword in text for keyword in market_keywords):
            return 'MARKET'
        
        # Check for LIMIT indicators
        if 'LIMIT' in text:
            return 'LIMIT'
        
        # Check for entry price pattern with @ or "at"
        # Pattern: "@ 2655" or "AT 1.0900"
        if re.search(r'[@]\s*\d+\.?\d*', text):
            return 'LIMIT'
        
        # Check for "at" followed by price (but not "at loss" or "at profit")
        if re.search(r'\bAT\s+\d+\.?\d*', text):
            return 'LIMIT'
        
        # Check for price after action+symbol pattern: "BUY EURUSD 1.0900" or "SELL XAUUSD 2655"
        # This pattern indicates a limit order with specific entry price
        if re.search(r'(BUY|SELL|LONG|SHORT)\s+[A-Z]+\s+\d+\.?\d+(?:\s|,|$)', text):
            return 'LIMIT'
        
        # DEFAULT: No entry price or keywords → MARKET order
        return 'MARKET'
    
    def _extract_entry_price(self, text: str) -> Optional[float]:
        """
        Extract entry price for LIMIT orders.
        
        Returns:
            float entry price or None if not found
        
        CRITICAL: Returns float (not int) for MT5 compatibility
        """
        # Pattern 1: "@ 2655.50" or "@2655"
        match = re.search(r'[@]\s*(\d+\.?\d*)', text)
        if match:
            return float(match.group(1))
        
        # Pattern 2: "at 1.0900" (but not "at loss" or "at profit")
        match = re.search(r'\bAT\s+(\d+\.?\d+)', text)
        if match:
            return float(match.group(1))
        
        # Pattern 3: "LIMIT 2655" or "limit 1.0900"
        match = re.search(r'LIMIT\s+(\d+\.?\d+)', text)
        if match:
            return float(match.group(1))
        
        # Pattern 4: Price after action+symbol: "BUY EURUSD 1.0900" or "SELL XAUUSD 2655"
        # This finds price directly after the symbol
        match = re.search(r'(BUY|SELL|LONG|SHORT)\s+[A-Z]+\s+(\d+\.?\d+)(?:\s|,|$)', text)
        if match:
            return float(match.group(2))
        
        # Pattern 5: "entry: 1.0900" or "price: 2655"
        match = re.search(r'(?:ENTRY|PRICE)[\s:]+(\d+\.?\d+)', text)
        if match:
            return float(match.group(1))
        
        return None
    
    def _extract_symbol(self, text: str) -> Optional[str]:
        """
        Extract symbol using SymbolResolver.
        
        Handles:
        - Aliases (GOLD → XAUUSD, BTC → BTCUSD)
        - Direct symbols (EURUSD, XAUUSD, US30)
        - Amplified indices (US30_x10, USTEC_x100)
        
        Returns:
            Official MT5 symbol or None
        """
        # Single source of truth for symbol resolution
        symbol = SymbolResolver.resolve(text)
        if symbol:
            logger.info(f"🔍 Resolved symbol: {symbol}")
        return symbol
    
    def _extract_price(self, text: str, price_type: str) -> Optional[float]:
        """
        Extract price value for SL or TP with multiple format support.

        Handles various formats:
        - "SL: 4014.427" / "sl: 4014.427"
        - "TP – 80000" / "tp – 80000"
        - "stop loss: 2650" / "Stop Loss: 2650"
        - "take profit: 2700" / "Take Profit: 2700"
        - "SL 4014.427" (space only)
        - "TP 80000" (space only)
        - "SL - 4,232.37" (comma thousand separator)
        - "TP - 4,205.58" (comma thousand separator)
        - "TP1 2645 TP2 2640 TP3 2635" (numbered TPs - use TP1 only)
        """
        text_upper = text.upper()

        # Build pattern based on price type
        # Pattern captures: digits with optional commas, optional decimal part
        # Examples: "4232.37", "4,232.37", "80000", "80,000"
        if price_type.upper() == 'TP':
            # NEW: Check for numbered TPs first (TP1, TP2, TP3)
            # Use TP1 only for simplicity
            tp1_match = re.search(r'TP\s*1\s*[:\s–-]*\s*([\d,]+(?:\.[\d]+)?)', text_upper)
            if tp1_match:
                try:
                    price_str = tp1_match.group(1).replace(',', '')
                    return float(price_str)
                except ValueError:
                    pass
            
            # Fallback: Match TP without number (original pattern)
            # Match: TP, tp, take profit, Take Profit, TAKE PROFIT
            # Use negative lookahead (?!\d) to exclude TP1, TP2, TP3 (number directly after TP)
            # But allow "TP 4519" (space between TP and price)
            pattern = r'(?:TP|TAKE\s*PROFIT)(?!\d)\s*[:\s–-]*\s*([\d,]+(?:\.[\d]+)?)'
        elif price_type.upper() == 'SL':
            # Match: SL, sl, stop loss, Stop Loss, STOP LOSS
            pattern = r'(?:SL|STOP\s*LOSS)\s*[:\s–-]*\s*([\d,]+(?:\.[\d]+)?)'
        else:
            return None

        match = re.search(pattern, text_upper, re.IGNORECASE)
        if match:
            try:
                # Remove commas before converting to float (handles "4,232.37" → "4232.37")
                price_str = match.group(1).replace(',', '')
                return float(price_str)
            except ValueError:
                logger.warning(f"Failed to convert '{match.group(1)}' to float for {price_type}")
                return None

        return None
    
    def is_signal_message(self, message_text: str) -> bool:
        """
        Quick check if message might contain a signal.
        Use before full parsing for efficiency.
        
        Updated to support:
        - Traditional signals (action + symbol + SL/TP)
        - Entry-only signals (action + symbol/alias)
        - Params-only signals (just SL/TP)
        - All symbol types (forex, metals, crypto, indices, energies)
        """
        if not message_text:
            return False
        
        # Normalize text first (same as parse() does)
        # This converts STOPLOSS→SL, TAKEPROFIT→TP, etc.
        text_normalized = self._normalize_text(message_text)
        
        # Check for action keywords (BUY, SELL, LONG, SHORT)
        has_action = any(word in text_normalized for word in ['BUY', 'SELL', 'LONG', 'SHORT'])
        
        # Check for symbol-like pattern (2-10 uppercase letters, optional _xN suffix)
        has_symbol = bool(re.search(r'[A-Z]{2,10}(?:_x\d+)?', text_normalized))
        
        # Check for common symbol aliases (expanded list)
        has_alias = any(alias in text_normalized for alias in [
            'GOLD', 'SILVER', 'PLATINUM', 'PALLADIUM', 'COPPER', 'ALUMINUM',
            'BITCOIN', 'BTC', 'ETH', 'ETHEREUM', 'LITECOIN', 'RIPPLE', 'CARDANO', 'SOLANA',
            'EUR', 'GBP', 'JPY', 'AUD', 'NZD', 'CAD', 'CHF',
            'CABLE', 'FIBER', 'AUSSIE', 'KIWI', 'LOONIE', 'SWISSIE', 'GOPHER',
            'OIL', 'CRUDE', 'BRENT', 'GAS', 'NATGAS',
            'DOW', 'NASDAQ', 'SPX', 'FTSE', 'DAX', 'NIKKEI'
        ])
        
        # Check for TP/SL keywords (now simplified - normalization already converted variants)
        has_params = 'TP' in text_normalized or 'SL' in text_normalized
        
        # Signal is valid if:
        # 1. Has action + (symbol OR alias), OR
        # 2. Has params (TP/SL)
        return (has_action and (has_symbol or has_alias)) or has_params


# === TESTING UTILITY ===
def test_parser():
    """Test parser with sample signals"""
    import sys
    import io
    
    # Fix Windows console encoding for emojis
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    parser = SignalParser()
    
    test_messages = [
        # BUY signals (COMPLETE)
        ("BUY #1", """Day 2 .. Buy XAUUSD ..Gold Now !
Stop loss : 4014.427
Take profit : 4055.964"""),
        
        ("BUY #2", """Buy XAUUSD .. Gold now !
Stop Loss : 4123.060
Take profit : 4143.328"""),
        
        ("BUY #3", """Buy XAUUSD .. Gold now !
Stop loss : 3986.492
Take Profit : 4007.452"""),
        
        # SELL signals (COMPLETE)
        ("SELL #1", """Mrbluemax Forex Academy
Sell XAUUSD .. Gold now
Stop loss :4046.138
Take Profit:4029.901"""),
        
        ("SELL #2", """Mrbluemax Forex Academy
Sell XAUUSD .. Gold now
Stop loss :4052.555
Take Profit:4030.353"""),
        
        # === NEW: LIMIT ORDER SUPPORT (Copy Bot Puneet) ===
        
        # Scenario 1: SHORT + MARKET (LONG/SHORT normalization)
        ("LIMIT #1 - SHORT MARKET", "Short market xau usd Sl - 4462 Tp1 -4401 Tp2 -4243"),
        
        # Scenario 2: LONG + MARKET
        ("LIMIT #2 - LONG MARKET", "XAGUSD LONG market Sl 75.4 Tp - 78.921"),
        
        # Scenario 3: BUY LIMIT with entry price
        ("LIMIT #3 - BUY LIMIT", "XAUUSD Buy Limit 4477 , Sl 4473 , Tp 4519"),
        
        # Scenario 4: SELL LIMIT
        ("LIMIT #4 - SELL LIMIT", "SELL EURUSD @ 1.0950 SL 1.0970 TP 1.0920"),
        
        # Multi-TP parsing (use TP1 only)
        ("MULTI-TP #1", "SELL XAUUSD @ 2655 SL 2665 TP1 2645 TP2 2640 TP3 2635"),
        
        # Spaced symbol normalization
        ("SPACED #1", "Buy xau usd @ 2650 SL 2640 TP 2660"),
        ("SPACED #2", "Short eur usd market SL 1.10 TP 1.05"),
        
        # === Two-message signal support ===
        
        # ENTRY_ONLY signals (action + symbol, no SL/TP)
        ("ENTRY_ONLY #1", "SELL GOLD NOW"),
        ("ENTRY_ONLY #2", "BUY BTC NOW"),
        ("ENTRY_ONLY #3", "BUY XAUUSD NOW"),
        ("ENTRY_ONLY #4", "SELL SILVER"),
        ("ENTRY_ONLY #5", "LONG GOLD MARKET"),  # LONG + MARKET
        ("ENTRY_ONLY #6", "SHORT EURUSD NOW"),  # SHORT
        
        # PARAMS_ONLY signals (SL/TP, no action/symbol)
        ("PARAMS_ONLY #1", "TP 2700 SL 2650"),
        ("PARAMS_ONLY #2", "SL: 80000\nTP: 95000"),
        ("PARAMS_ONLY #3", "take profit: 2700\nstop loss: 2650"),
        ("PARAMS_ONLY #4", "TP – 4055.964\nSL – 4014.427"),
        
        # Edge case: PARAMS_ONLY with no spaces (the bug we're fixing)
        ("PARAMS_NOSPACE #1", "stoploss 80000 takeprofit 95000"),
        ("PARAMS_NOSPACE #2", "STOPLOSS 2650 TAKEPROFIT 2700"),
        ("PARAMS_HYPHEN #1", "stop-loss 80000 take-profit 95000"),
        ("PARAMS_MIXED #1", "StopLoss: 80000\nTakeProfit: 95000"),
        
        # TP/SL format variations
        ("TP_FORMAT #1", "tp: 2700"),
        ("TP_FORMAT #2", "take profit - 2700"),
        ("TP_FORMAT #3", "Take Profit 2700"),
        ("SL_FORMAT #1", "sl: 2650"),
        ("SL_FORMAT #2", "stop loss - 2650"),
        ("SL_FORMAT #3", "Stop Loss 2650"),
        
        # Symbol alias resolution
        ("ALIAS #1", "BUY GOLD SL 2650 TP 2700"),
        ("ALIAS #2", "SELL SILVER NOW"),
        ("ALIAS #3", "BUY BITCOIN SL 80000 TP 95000"),
        ("ALIAS #4", "SELL CABLE SL 1.25 TP 1.22"),  # GBPUSD nickname
        ("ALIAS #5", "BUY FIBER SL 1.05 TP 1.10"),  # EURUSD nickname
        ("ALIAS #6", "SELL AUSSIE NOW"),  # AUDUSD nickname
        ("ALIAS #7", "BUY COPPER SL 4.50 TP 4.80"),  # Industrial metal
        
        # === NEW: Forex Exotics ===
        ("EXOTIC #1", "BUY USDTRY SL 32.5 TP 33.0"),
        ("EXOTIC #2", "SELL EURZAR SL 20.5 TP 19.8"),
        ("EXOTIC #3", "BUY USDMXN NOW"),
        
        # === NEW: Indices ===
        ("INDEX #1", "BUY US30 SL 40000 TP 42000"),
        ("INDEX #2", "SELL USTEC SL 16000 TP 15500"),
        ("INDEX #3", "BUY UK100 SL 7500 TP 7700"),
        ("INDEX #4", "SELL DE30 NOW"),
        ("INDEX #5", "BUY JP225 SL 33000 TP 34000"),
        
        # === NEW: Amplified Indices ===
        ("AMPLIFIED #1", "BUY US30_x10 SL 400000 TP 420000"),
        ("AMPLIFIED #2", "SELL USTEC_x100 NOW"),
        ("AMPLIFIED #3", "BUY US500_x100 SL 450000 TP 460000"),
        
        # === NEW: Energies ===
        ("ENERGY #1", "BUY OIL SL 70 TP 75"),
        ("ENERGY #2", "SELL BRENT SL 75 TP 72"),
        ("ENERGY #3", "BUY NATGAS SL 3.5 TP 4.0"),

        # === COMMA-SEPARATED PRICES (Cobalt SMC format) ===
        ("COMMA #1", """Cobalt SMC
SELL GOLD NOW

SL - 4,232.37
TP - 4,205.58"""),

        ("COMMA #2", """BUY GOLD NOW
SL - 3,986.50
TP - 4,050.00"""),

        ("COMMA #3", "SL - 80,000.50\nTP - 95,000.75"),  # PARAMS_ONLY with commas

        ("COMMA #4", """Buy XAUUSD now
Stop loss: 4,123.060
Take profit: 4,200.500"""),

        # Edge cases: mixed formats (comma and non-comma)
        ("MIXED #1", "SL 4232.37 TP 4,205.58"),  # One with comma, one without
        ("MIXED #2", "SL - 4,232 TP - 4205"),    # Integer with comma vs without

        # Non-signals (should return None)
        ("NON-SIGNAL #1", "I need to teach you guys this my new strategy, it's too good !"),
        ("NON-SIGNAL #2", "That's what I went to learn when i traveled out !"),
        ("NON-SIGNAL #3", "React if you're ready to learn"),
    ]
    
    print("\n" + "="*60)
    print("SIGNAL PARSER TEST")
    print("="*60)
    
    passed = 0
    failed = 0
    
    for name, msg in test_messages:
        print(f"\n--- {name} ---")
        preview = msg.replace('\n', ' ')[:50]
        print(f"Message: {preview}...")
        result = parser.parse(msg)
        
        if result:
            order_info = f" | Order: {result.order_type}" + (f" @ {result.entry_price}" if result.entry_price else "")
            print(f"[OK] Parsed: {result.action} {result.symbol}{order_info} | SL: {result.stop_loss} | TP: {result.take_profit}")
            if "NON-SIGNAL" in name:
                print("    [WARN] This should NOT have been detected as signal!")
                failed += 1
            else:
                passed += 1
        else:
            print("[--] No signal detected")
            if "NON-SIGNAL" in name:
                passed += 1
            else:
                print("    [FAIL] Expected to find a signal!")
                failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)


if __name__ == '__main__':
    test_parser()

