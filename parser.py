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

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Parsed trading signal data"""
    action: str              # BUY, SELL, or CLOSE
    symbol: str              # e.g., XAUUSD
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


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
            if not action:
                logger.debug(f"No action found in: {message_text[:50]}...")
                return None
            
            # === STEP 3: Extract symbol ===
            symbol = self._extract_symbol(text)
            if not symbol:
                logger.debug(f"No valid symbol found in: {message_text[:50]}...")
                return None
            
            # === STEP 4: For CLOSE signals, we don't need SL/TP ===
            if action == 'CLOSE':
                logger.info(f"📍 Parsed CLOSE signal: {symbol}")
                return Signal(action='CLOSE', symbol=symbol)
            
            # === STEP 5: Extract Stop Loss and Take Profit ===
            stop_loss = self._extract_price(text, 'SL')
            take_profit = self._extract_price(text, 'TP')
            
            # Validate that we have at least SL for BUY/SELL
            if stop_loss is None:
                logger.warning(f"No stop loss found for {action} {symbol}")
                # Still return signal but without SL - user may want to set manually
            
            logger.info(f"📍 Parsed signal: {action} {symbol} | SL: {stop_loss} | TP: {take_profit}")
            return Signal(
                action=action,
                symbol=symbol,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
        except Exception as e:
            logger.error(f"Parsing error: {e}")
            return None
    
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
            '..GOLD': '',      # Remove Gold suffix
            '.. GOLD': '',     # Remove Gold suffix with space
            'GOLD NOW': '',    # Remove "Gold Now"
            'NOW !': '',       # Remove trailing "Now !"
            'NOW!': '',
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
        """Extract forex symbol from text"""
        # Pattern: 6-7 uppercase letters (forex pairs)
        # Common patterns: XAUUSD, EURUSD, GBPJPY, etc.
        symbol_pattern = r'\b([A-Z]{6,7})\b'
        matches = re.findall(symbol_pattern, text)
        
        for match in matches:
            # Validate against known symbols
            if match in self.valid_symbols:
                return match
            # Also accept any 6-char forex pair format (XXX/XXX)
            if len(match) == 6 and match[:3] != match[3:]:
                return match
        
        return None
    
    def _extract_price(self, text: str, price_type: str) -> Optional[float]:
        """
        Extract price value for SL or TP.

        Handles various formats:
        - "SL : 4014.427" (decimal with colon)
        - "SL: 80000" (integer with colon)
        - "SL – 80000" (integer with em-dash)
        - "SL – 1.0820" (decimal with em-dash)
        - "SL 4014.427" (decimal with space only)
        - "SL 80000" (integer with space only)
        """
        # Pattern: keyword + optional separators (colon, em-dash, hyphen, space) + number (integer OR decimal)
        # (?:\.[\d]+)? makes the decimal part optional
        pattern = rf'{price_type}\s*[:\s–-]*\s*([\d]+(?:\.[\d]+)?)'

        match = re.search(pattern, text)
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
        """
        if not message_text:
            return False
        
        text_upper = message_text.upper()
        
        # Must have action keyword
        has_action = any(word in text_upper for word in ['BUY', 'SELL', 'CLOSE'])
        
        # Must have symbol-like pattern
        has_symbol = bool(re.search(r'[A-Z]{6,7}', text_upper))
        
        return has_action and has_symbol


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
        # BUY signals
        ("BUY #1", """Day 2 .. Buy XAUUSD ..Gold Now !
Stop loss : 4014.427
Take profit : 4055.964"""),
        
        ("BUY #2", """Buy XAUUSD .. Gold now !
Stop Loss : 4123.060
Take profit : 4143.328"""),
        
        ("BUY #3", """Buy XAUUSD .. Gold now !
Stop loss : 3986.492
Take Profit : 4007.452"""),
        
        # SELL signals
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

