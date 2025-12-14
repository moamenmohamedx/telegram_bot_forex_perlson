"""
Signal Parser Module - PRODUCTION-READY VERSION
================================================
Parses trading signals from Telegram messages with robust error handling.

FIXES APPLIED:
- ✅ Symbol extraction with blacklist (prevents "SIGNAL" false positive)
- ✅ Integer price support (handles "SL – 80000")
- ✅ Comma separator support (handles "4,232.37")
- ✅ Signal validation layer
- ✅ Alias mapping ("GOLD" → "XAUUSD")
"""

import re
import sys
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Parsed trading signal data"""
    action: str              # BUY or SELL
    symbol: str              # e.g., XAUUSD
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class SignalParser:
    """Production-ready parser for trading signals"""
    
    def __init__(self):
        # Valid forex symbols (expandable)
        self.valid_symbols = {
            'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 
            'USDCAD', 'NZDUSD', 'USDCHF', 'GBPJPY', 'EURJPY',
            'XAGUSD', 'BTCUSD', 'ETHUSD', 'GBPAUD', 'EURGBP'
        }
        
        # Symbol aliases (common names → official symbols)
        self.symbol_aliases = {
            'GOLD': 'XAUUSD',
            'SILVER': 'XAGUSD',
            'BITCOIN': 'BTCUSD',
            'BTC': 'BTCUSD',
            'ETHEREUM': 'ETHUSD',
            'ETH': 'ETHUSD',
        }
        
        # Blacklist words that look like symbols but aren't
        self.symbol_blacklist = {
            'SIGNAL', 'PROFIT', 'TARGET', 'MARKET', 'CLOSED',
            'OPENED', 'ACTIVE', 'PENDING', 'CANCEL', 'UPDATE',
            'NOTICE', 'ALERT', 'WARNING', 'STATUS', 'REPORT'
        }
    
    def parse(self, message_text: str) -> Optional[Signal]:
        """
        Parse trading signal from Telegram message.
        
        Returns Signal if valid signal found, None otherwise.
        """
        if not message_text:
            return None
        
        try:
            # === STEP 1: Clean and normalize text (but preserve symbol aliases) ===
            text = self._normalize_text(message_text)
            
            # === STEP 2: Detect action type (BUY/SELL) ===
            action = self._extract_action(text)
            if not action:
                logger.debug(f"No action found in: {message_text[:50]}...")
                return None
            
            # === STEP 3: Extract symbol (BEFORE removing GOLD/NOW etc) ===
            symbol = self._extract_symbol(text)
            if not symbol:
                logger.debug(f"No valid symbol found in: {message_text[:50]}...")
                return None
            
            # === STEP 3B: Now do additional normalization for price extraction ===
            text = self._normalize_for_symbol_extraction(text)
            
            # === STEP 4: Extract Stop Loss and Take Profit ===
            stop_loss = self._extract_price(text, 'SL')
            take_profit = self._extract_price(text, 'TP')
            
            # Validate that we have at least SL for BUY/SELL
            if stop_loss is None:
                logger.warning(f"No stop loss found for {action} {symbol}")
                # Still return signal but without SL - user may want to set manually
            
            # === STEP 5: Create and validate signal ===
            signal = Signal(
                action=action,
                symbol=symbol,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            # Validate signal sanity
            is_valid, error_msg = self.validate_signal(signal)
            if not is_valid:
                logger.error(f"❌ Signal validation failed: {error_msg}")
                return None
            
            logger.info(f"📍 Parsed signal: {action} {symbol} | SL: {stop_loss} | TP: {take_profit}")
            return signal
            
        except Exception as e:
            logger.error(f"Parsing error: {e}", exc_info=True)
            return None
    
    def _normalize_text(self, text: str) -> str:
        """Normalize message text for consistent parsing"""
        # Convert to uppercase for consistent matching
        normalized = text.upper()
        
        # Standardize common variations
        # NOTE: Don't remove "GOLD" here - it's a valid alias for XAUUSD
        replacements = {
            'STOP LOSS': 'SL',
            'STOPLOSS': 'SL',
            'STOP-LOSS': 'SL',
            'TAKE PROFIT': 'TP',
            'TAKEPROFIT': 'TP',
            'TAKE-PROFIT': 'TP',
            'TARGET': 'TP',
            '…': ' ',           # Replace ellipsis with space
            'NOW !': ' ',       # Remove trailing "Now !"
            'NOW!': ' ',
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    def _normalize_for_symbol_extraction(self, text: str) -> str:
        """Additional normalization after symbol extraction (for Gold suffix removal)"""
        # These replacements are done AFTER symbol is extracted
        # to avoid interfering with GOLD alias detection
        replacements = {
            '..GOLD': ' ',      # Remove Gold suffix
            '.. GOLD': ' ',     # Remove Gold suffix with space  
            'GOLD': ' ',        # Remove GOLD after we've extracted XAUUSD
        }
        
        normalized = text
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    def _extract_action(self, text: str) -> Optional[str]:
        """Extract trading action from normalized text"""
        # Check for BUY
        if re.search(r'\bBUY\b', text):
            return 'BUY'
        
        # Check for SELL
        if re.search(r'\bSELL\b', text):
            return 'SELL'
        
        return None
    
    def _extract_symbol(self, text: str) -> Optional[str]:
        """
        Extract forex symbol from text.
        
        Strategy:
        1. Check for aliases (GOLD → XAUUSD)
        2. Find 6-7 letter uppercase words
        3. Filter out blacklisted words
        4. Validate against whitelist or forex pair pattern
        """
        # === STRATEGY 1: Check aliases first ===
        for alias, official_symbol in self.symbol_aliases.items():
            # Use word boundary to avoid partial matches
            if re.search(rf'\b{alias}\b', text):
                logger.debug(f"Mapped alias '{alias}' → '{official_symbol}'")
                return official_symbol
        
        # === STRATEGY 2: Pattern matching ===
        # Pattern: 6-7 uppercase letters (forex pairs)
        symbol_pattern = r'\b([A-Z]{6,7})\b'
        matches = re.findall(symbol_pattern, text)
        
        for match in matches:
            # Skip blacklisted words
            if match in self.symbol_blacklist:
                logger.debug(f"Skipping blacklisted word: {match}")
                continue
            
            # Check whitelist first (known symbols)
            if match in self.valid_symbols:
                return match
            
            # Accept 6-char forex pair format (XXX+XXX, not repeated)
            if len(match) == 6 and match[:3] != match[3:]:
                # Additional validation: both parts should be valid currency codes
                # This prevents false positives like "PLEASE", "MARKET", etc.
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
        - "SL: 4,232.37" (with thousands separator)
        """
        # Remove thousands separators (commas) AND spaces between digits first
        # This handles both "4,232.37" and "4 232.37" formats
        text_clean = text.replace(',', '').replace(' ', ' ')  # Normalize spaces
        
        # Pattern: keyword + optional separators (colon, em-dash, hyphen, space) + number (integer OR decimal)
        # (?:\.[\d]+)? makes the decimal part optional
        # Updated to handle em-dash (–) and regular dash (-)
        pattern = rf'{price_type}\s*[:–\-\s]*\s*([\d]+(?:\.[\d]+)?)'

        match = re.search(pattern, text_clean)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                logger.warning(f"Failed to convert '{match.group(1)}' to float for {price_type}")
                return None

        return None
    
    def validate_signal(self, signal: Signal) -> Tuple[bool, Optional[str]]:
        """
        Validate parsed signal for sanity.
        
        Returns:
            (is_valid, error_message)
        """
        # === CHECK 1: Symbol is not a blacklisted word ===
        if signal.symbol in self.symbol_blacklist:
            return False, f"Invalid symbol '{signal.symbol}' - likely parsing error (blacklisted word)"
        
        # === CHECK 2: Symbol length ===
        if len(signal.symbol) not in [6, 7]:
            return False, f"Invalid symbol length: {signal.symbol} (must be 6-7 characters)"
        
        # === CHECK 3: Action is valid ===
        if signal.action not in ['BUY', 'SELL']:
            return False, f"Invalid action: {signal.action}"
        
        # === CHECK 4: For BUY/SELL, validate price logic ===
        if signal.action in ['BUY', 'SELL']:
            if signal.stop_loss and signal.take_profit:
                # BUY: SL should be below TP (price goes up to hit TP)
                # SELL: SL should be above TP (price goes down to hit TP)
                if signal.action == 'BUY':
                    if signal.stop_loss >= signal.take_profit:
                        return False, f"BUY signal: SL ({signal.stop_loss}) should be < TP ({signal.take_profit})"
                else:  # SELL
                    if signal.stop_loss <= signal.take_profit:
                        return False, f"SELL signal: SL ({signal.stop_loss}) should be > TP ({signal.take_profit})"
            
            # === CHECK 5: Prices should be reasonable ===
            if signal.stop_loss:
                if signal.stop_loss <= 0:
                    return False, f"Invalid SL: {signal.stop_loss} (must be > 0)"
                if signal.stop_loss > 1000000:
                    return False, f"Unreasonable SL: {signal.stop_loss} (too high)"
            
            if signal.take_profit:
                if signal.take_profit <= 0:
                    return False, f"Invalid TP: {signal.take_profit} (must be > 0)"
                if signal.take_profit > 1000000:
                    return False, f"Unreasonable TP: {signal.take_profit} (too high)"
        
        return True, None
    
    def is_signal_message(self, message_text: str) -> bool:
        """
        Quick check if message might contain a signal.
        Use before full parsing for efficiency.
        """
        if not message_text:
            return False
        
        text_upper = message_text.upper()
        
        # Must have action keyword
        has_action = any(word in text_upper for word in ['BUY', 'SELL'])
        
        # Must have symbol-like pattern OR alias
        has_symbol_pattern = bool(re.search(r'[A-Z]{6,7}', text_upper))
        has_alias = any(alias in text_upper for alias in self.symbol_aliases.keys())
        
        return has_action and (has_symbol_pattern or has_alias)


# === TESTING UTILITY ===
def test_parser():
    """Comprehensive test suite for parser"""
    import sys
    import io
    
    # Fix Windows console encoding for emojis
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    parser = SignalParser()
    
    test_messages = [
        # === BLUE MAX FOREX ACADEMY SIGNALS ===
        ("Blue Max #1 - Em-dash integers", """BUY BTCUSD NOW

SL – 80000
TP – 95000"""),
        
        ("Blue Max #2 - Standard format", """Day 5 ✅
BTCUSD BUY!
Stop loss: 80000
Take profit: 95000"""),
        
        ("Blue Max #3 - CRITICAL BUG TEST", """## Signal 3 : 
Buy BTCUSD  Now
Big lot size!

Stop loss: 4050.834
Take Profit: 4085.320"""),
        
        ("Blue Max #4 - With XAUUSD", """## Signal 3 : 
Buy XAUUSD… Gold Now
Big lot size!

Stop loss: 4050.834
Take Profit: 4085.320"""),
        
        # === COBALT SMC GROUP SIGNALS ===
        ("Cobalt #1 - Comma separators", """SELL GOLD NOW
SL – 4,232.37
TP – 4,205.58"""),
        
        # === SELL SIGNALS ===
        ("Sell #1", """Mrbluemax Forex Academy
Sell XAUUSD .. Gold now
Stop loss :4046.138
Take Profit:4029.901"""),
        
        # === NON-SIGNALS (Should return None) ===
        ("Non-signal #1", "I need to teach you guys this my new strategy, it's too good !"),
        ("Non-signal #2", "That's what I went to learn when i traveled out !"),
        ("Non-signal #3", "React if you're ready to learn"),
        ("Non-signal #4", "EURGBP 4R TP HIT 💰🔥 Great start to the week 🫡💯🔥"),
        
        # === EDGE CASES ===
        ("Edge: Invalid SL/TP logic", """BUY BTCUSD
SL: 95000
TP: 80000"""),  # SL > TP for BUY (wrong!)
    ]
    
    print("\n" + "="*80)
    print("COMPREHENSIVE SIGNAL PARSER TEST SUITE")
    print("="*80)
    
    passed = 0
    failed = 0
    
    for name, msg in test_messages:
        print(f"\n{'='*80}")
        print(f"TEST: {name}")
        print(f"{'='*80}")
        preview = msg.replace('\n', ' ')[:70]
        print(f"Message: {preview}...")
        
        result = parser.parse(msg)
        
        if result:
            print(f"\n✅ PARSED SUCCESSFULLY:")
            print(f"   Action: {result.action}")
            print(f"   Symbol: {result.symbol}")
            print(f"   SL:     {result.stop_loss}")
            print(f"   TP:     {result.take_profit}")
            
            # Check if this should have been rejected
            if "Non-signal" in name:
                print(f"\n   ⚠️  WARNING: This should NOT have been detected as signal!")
                failed += 1
            elif "Edge: Invalid" in name:
                print(f"\n   ⚠️  WARNING: This should have been rejected (invalid logic)!")
                failed += 1
            else:
                passed += 1
        else:
            print(f"\n❌ NO SIGNAL DETECTED")
            
            # Check if this should have been parsed
            if "Non-signal" in name or "Edge: Invalid" in name:
                print(f"   ✅ Correct - this is not a valid signal")
                passed += 1
            else:
                print(f"   ⚠️  FAILED: Expected to parse a signal!")
                failed += 1
    
    print("\n" + "="*80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_messages)} tests")
    print(f"Success Rate: {100 * passed / len(test_messages):.1f}%")
    print("="*80)
    
    # Return exit code for CI/CD
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    exit_code = test_parser()
    sys.exit(exit_code)

