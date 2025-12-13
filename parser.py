"""
Signal Parser Module
====================
Parses trading signals from Mrbluemax Forex Academy Telegram messages.

Signal Formats Supported:
-------------------------
BUY:  "Buy XAUUSD .. Gold now !" + "Stop loss : 4014.427" + "Take profit : 4055.964"
SELL: "Sell XAUUSD .. Gold now ⬇️" + "Stop loss :4046.138" + "Take Profit:4029.901"
CLOSE: "Close XAUUSD..Gold on 100 pips Now !" or "Close now on 100 pips"
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
    action: Optional[str]              # BUY, SELL, CLOSE, or None
    symbol: Optional[str]              # e.g., XAUUSD, or None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # NEW: Multi-message support fields
    is_complete: bool = False          # True if has action+symbol+SL/TP
    signal_type: str = 'UNKNOWN'       # COMPLETE, ENTRY_ONLY, PARAMS_ONLY, INVALID
    
    def __str__(self) -> str:
        """Human-readable representation"""
        if self.signal_type == 'COMPLETE':
            return f"{self.action} {self.symbol} | SL: {self.stop_loss} | TP: {self.take_profit}"
        elif self.signal_type == 'ENTRY_ONLY':
            return f"{self.action} {self.symbol} (no SL/TP)"
        elif self.signal_type == 'PARAMS_ONLY':
            return f"SL: {self.stop_loss} | TP: {self.take_profit}"
        return "INVALID"


class SignalParser:
    """Parser for Mrbluemax Forex Academy trading signals"""
    
    def __init__(self):
        # Valid forex symbols (add more as needed)
        self.valid_symbols = {
            'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 
            'USDCAD', 'NZDUSD', 'USDCHF', 'GBPJPY', 'EURJPY',
            'XAGUSD', 'BTCUSD', 'ETHUSD'
        }
    
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
            
            # === STEP 2: Detect action type (BUY/SELL/CLOSE) ===
            action = self._extract_action(text)
            
            # === STEP 3: Extract symbol ===
            symbol = self._extract_symbol(text)
            
            # === STEP 4: Extract Stop Loss and Take Profit ===
            stop_loss = self._extract_price(text, 'SL')
            take_profit = self._extract_price(text, 'TP')
            
            # === STEP 5: For CLOSE signals (special handling) ===
            if action == 'CLOSE' and symbol:
                logger.info(f"📍 Parsed CLOSE signal: {symbol}")
                return Signal(action='CLOSE', symbol=symbol)
            
            # Log warnings for incomplete signals
            if action and symbol and not stop_loss and not take_profit:
                logger.warning(f"No stop loss found for {action} {symbol}")
            
            # === STEP 6: Create signal object ===
            signal = Signal(
                action=action,
                symbol=symbol,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            # === STEP 7: Classify signal completeness ===
            signal.signal_type = self.classify_signal(signal)
            
            # === STEP 8: Validate and return ===
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
        """Extract trading action from normalized text"""
        # Check for CLOSE first (most specific)
        if re.search(r'\bCLOSE\b', text):
            return 'CLOSE'
        
        # Check for BUY
        if re.search(r'\bBUY\b', text):
            return 'BUY'
        
        # Check for SELL
        if re.search(r'\bSELL\b', text):
            return 'SELL'
        
        return None
    
    def _extract_symbol(self, text: str) -> Optional[str]:
        """
        Extract symbol using multi-strategy approach.
        
        Strategy 1: Direct 6-7 char symbol match (XAUUSD, BTCUSD)
        Strategy 2: Alias resolution (GOLD → XAUUSD)
        
        Returns:
            Official MT5 symbol or None
        """
        # Strategy 1: Try alias resolution FIRST (more comprehensive)
        alias_symbol = SymbolResolver.resolve(text)
        if alias_symbol:
            logger.info(f"🔍 Resolved alias to: {alias_symbol}")
            return alias_symbol
        
        # Strategy 2: Direct symbol match fallback (for symbols not in alias map)
        symbol_pattern = r'\b([A-Z]{6,7})\b'
        matches = re.findall(symbol_pattern, text)
        
        for match in matches:
            # Validate against known symbols
            if match in self.valid_symbols:
                return match
        
        return None
    
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
        """
        text_upper = text.upper()
        
        # Build pattern based on price type
        if price_type.upper() == 'TP':
            # Match: TP, tp, take profit, Take Profit, TAKE PROFIT
            pattern = r'(?:TP|TAKE\s*PROFIT)\s*[:\s–-]*\s*([\d]+(?:\.[\d]+)?)'
        elif price_type.upper() == 'SL':
            # Match: SL, sl, stop loss, Stop Loss, STOP LOSS
            pattern = r'(?:SL|STOP\s*LOSS)\s*[:\s–-]*\s*([\d]+(?:\.[\d]+)?)'
        else:
            return None

        match = re.search(pattern, text_upper, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
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
        """
        if not message_text:
            return False
        
        text_upper = message_text.upper()
        
        # Check for action keywords (BUY, SELL, CLOSE)
        has_action = any(word in text_upper for word in ['BUY', 'SELL', 'CLOSE'])
        
        # Check for symbol-like pattern (6-7 uppercase letters)
        has_symbol = bool(re.search(r'[A-Z]{6,7}', text_upper))
        
        # Check for symbol aliases (GOLD, BTC, SILVER, etc.)
        has_alias = any(alias in text_upper for alias in [
            'GOLD', 'SILVER', 'BITCOIN', 'BTC', 'ETH', 'ETHEREUM',
            'EUR', 'GBP', 'CABLE', 'AUSSIE', 'LOONIE', 'OIL'
        ])
        
        # Check for TP/SL keywords (for PARAMS_ONLY signals)
        has_params = any(keyword in text_upper for keyword in [
            'TP', 'SL', 'TAKE PROFIT', 'STOP LOSS'
        ])
        
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
        
        # CLOSE signals
        ("CLOSE #1", "Close XAUUSD..Gold on 100 pips Now !"),
        ("CLOSE #2", "Close XAUUSD now on 100 pips"),
        
        # === NEW: Two-message signal support ===
        
        # ENTRY_ONLY signals (action + symbol, no SL/TP)
        ("ENTRY_ONLY #1", "SELL GOLD NOW"),
        ("ENTRY_ONLY #2", "BUY BTC NOW"),
        ("ENTRY_ONLY #3", "BUY XAUUSD NOW"),
        ("ENTRY_ONLY #4", "SELL SILVER"),
        
        # PARAMS_ONLY signals (SL/TP, no action/symbol)
        ("PARAMS_ONLY #1", "TP 2700 SL 2650"),
        ("PARAMS_ONLY #2", "SL: 80000\nTP: 95000"),
        ("PARAMS_ONLY #3", "take profit: 2700\nstop loss: 2650"),
        ("PARAMS_ONLY #4", "TP – 4055.964\nSL – 4014.427"),
        
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
            print(f"[OK] Parsed: {result.action} {result.symbol} | SL: {result.stop_loss} | TP: {result.take_profit}")
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

