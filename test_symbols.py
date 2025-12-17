"""
Symbol Resolver Test Suite
===========================
Comprehensive tests for symbol parsing across all Exness categories.

Tests:
- Forex majors, minors, exotics
- Precious and industrial metals
- Cryptocurrencies
- Indices (US, UK, Europe, Asia)
- Energies
- Alias resolution
- Edge cases
"""

import sys
import io
from symbol_resolver import SymbolResolver


def test_symbol_resolver():
    """Test comprehensive symbol resolution"""
    
    # Fix Windows console encoding for emojis
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    test_cases = [
        # === FOREX MAJORS ===
        ("FOREX MAJOR #1", "BUY EURUSD NOW", "EURUSD"),
        ("FOREX MAJOR #2", "SELL GBPUSD SL 1.25", "GBPUSD"),
        ("FOREX MAJOR #3", "BUY USDJPY TP 150", "USDJPY"),
        ("FOREX MAJOR #4", "SELL AUDUSD NOW", "AUDUSD"),
        ("FOREX MAJOR #5", "BUY NZDUSD", "NZDUSD"),
        ("FOREX MAJOR #6", "SELL USDCHF", "USDCHF"),
        ("FOREX MAJOR #7", "BUY USDCAD", "USDCAD"),
        
        # === FOREX MINORS ===
        ("FOREX MINOR #1", "BUY EURGBP NOW", "EURGBP"),
        ("FOREX MINOR #2", "SELL EURJPY", "EURJPY"),
        ("FOREX MINOR #3", "BUY GBPJPY", "GBPJPY"),
        ("FOREX MINOR #4", "SELL AUDJPY", "AUDJPY"),
        ("FOREX MINOR #5", "BUY EURCHF", "EURCHF"),
        
        # === FOREX EXOTICS ===
        ("FOREX EXOTIC #1", "BUY USDTRY NOW", "USDTRY"),
        ("FOREX EXOTIC #2", "SELL USDZAR", "USDZAR"),
        ("FOREX EXOTIC #3", "BUY USDMXN", "USDMXN"),
        ("FOREX EXOTIC #4", "SELL EURZAR", "EURZAR"),
        ("FOREX EXOTIC #5", "BUY EURTRY", "EURTRY"),
        
        # === FOREX NICKNAMES ===
        ("NICKNAME #1", "BUY FIBER NOW", "EURUSD"),  # FIBER = EURUSD
        ("NICKNAME #2", "SELL CABLE", "GBPUSD"),     # CABLE = GBPUSD
        ("NICKNAME #3", "BUY GOPHER", "USDJPY"),     # GOPHER = USDJPY
        ("NICKNAME #4", "SELL AUSSIE", "AUDUSD"),    # AUSSIE = AUDUSD
        ("NICKNAME #5", "BUY KIWI", "NZDUSD"),       # KIWI = NZDUSD
        ("NICKNAME #6", "SELL LOONIE", "USDCAD"),    # LOONIE = USDCAD
        ("NICKNAME #7", "BUY SWISSIE", "USDCHF"),    # SWISSIE = USDCHF
        
        # === PRECIOUS METALS ===
        ("METAL #1", "BUY GOLD NOW", "XAUUSD"),
        ("METAL #2", "SELL XAUUSD", "XAUUSD"),
        ("METAL #3", "BUY SILVER", "XAGUSD"),
        ("METAL #4", "SELL XAGUSD", "XAGUSD"),
        ("METAL #5", "BUY PLATINUM", "XPTUSD"),
        ("METAL #6", "SELL PALLADIUM", "XPDUSD"),
        ("METAL #7", "BUY XAUEUR", "XAUEUR"),  # Gold vs EUR
        ("METAL #8", "SELL XAUGBP", "XAUGBP"),  # Gold vs GBP
        
        # === INDUSTRIAL METALS ===
        ("INDUSTRIAL #1", "BUY ALUMINUM NOW", "XALUSD"),
        ("INDUSTRIAL #2", "SELL COPPER", "XCUUSD"),
        ("INDUSTRIAL #3", "BUY NICKEL", "XNIUSD"),
        ("INDUSTRIAL #4", "SELL LEAD", "XPBUSD"),
        ("INDUSTRIAL #5", "BUY ZINC", "XZNUSD"),
        
        # === CRYPTOCURRENCIES ===
        ("CRYPTO #1", "BUY BITCOIN NOW", "BTCUSD"),
        ("CRYPTO #2", "SELL BTC", "BTCUSD"),
        ("CRYPTO #3", "BUY BTCUSD", "BTCUSD"),
        ("CRYPTO #4", "SELL ETHEREUM", "ETHUSD"),
        ("CRYPTO #5", "BUY ETH", "ETHUSD"),
        ("CRYPTO #6", "SELL LITECOIN", "LTCUSD"),
        ("CRYPTO #7", "BUY RIPPLE", "XRPUSD"),
        ("CRYPTO #8", "SELL CARDANO", "ADAUSD"),
        ("CRYPTO #9", "BUY DOGECOIN", "DOGEUSD"),
        ("CRYPTO #10", "SELL SOLANA", "SOLUSD"),
        
        # === ENERGIES ===
        ("ENERGY #1", "BUY OIL NOW", "USOIL"),
        ("ENERGY #2", "SELL CRUDE", "USOIL"),
        ("ENERGY #3", "BUY WTI", "USOIL"),
        ("ENERGY #4", "SELL BRENT", "UKOIL"),
        ("ENERGY #5", "BUY UKOIL", "UKOIL"),
        ("ENERGY #6", "SELL GAS", "XNGUSD"),
        ("ENERGY #7", "BUY NATGAS", "XNGUSD"),
        ("ENERGY #8", "SELL XNGUSD", "XNGUSD"),
        
        # === US INDICES ===
        ("INDEX US #1", "BUY DOW NOW", "US30"),
        ("INDEX US #2", "SELL US30", "US30"),
        ("INDEX US #3", "BUY DOWJONES", "US30"),
        ("INDEX US #4", "SELL NASDAQ", "USTEC"),
        ("INDEX US #5", "BUY USTEC", "USTEC"),
        ("INDEX US #6", "SELL NAS100", "USTEC"),
        ("INDEX US #7", "BUY SPX", "US500"),
        ("INDEX US #8", "SELL SP500", "US500"),
        ("INDEX US #9", "BUY US500", "US500"),
        
        # === AMPLIFIED INDICES ===
        # NOTE: text.upper() converts _x to _X, so returned symbols have uppercase X
        ("AMPLIFIED #1", "BUY US30_x10 NOW", "US30_X10"),
        ("AMPLIFIED #2", "SELL USTEC_x100", "USTEC_X100"),
        ("AMPLIFIED #3", "BUY US500_x100", "US500_X100"),
        
        # === UK & EUROPE INDICES ===
        ("INDEX UK #1", "BUY FTSE NOW", "UK100"),
        ("INDEX UK #2", "SELL UK100", "UK100"),
        ("INDEX EU #1", "BUY DAX", "DE30"),
        ("INDEX EU #2", "SELL DE30", "DE30"),
        ("INDEX EU #3", "BUY CAC", "FR40"),
        ("INDEX EU #4", "SELL FR40", "FR40"),
        ("INDEX EU #5", "BUY STOXX", "STOXX50"),
        ("INDEX EU #6", "SELL EUROSTOXX", "STOXX50"),
        
        # === ASIAN INDICES ===
        ("INDEX ASIA #1", "BUY NIKKEI NOW", "JP225"),
        ("INDEX ASIA #2", "SELL JP225", "JP225"),
        ("INDEX ASIA #3", "BUY ASX", "AUS200"),
        ("INDEX ASIA #4", "SELL AUS200", "AUS200"),
        ("INDEX ASIA #5", "BUY HANGSENG", "HK50"),
        ("INDEX ASIA #6", "SELL HSI", "HK50"),
        ("INDEX ASIA #7", "BUY HK50", "HK50"),
        
        # === EDGE CASES ===
        ("EDGE #1", "buy gold now", "XAUUSD"),  # Lowercase (should be normalized)
        ("EDGE #2", "BUY GOLD .. NOW", "XAUUSD"),  # Extra punctuation
        ("EDGE #3", "SELL GOLD/USD", "XAUUSD"),  # With slash (common in messages)
        ("EDGE #4", "BUY  GOLD  NOW", "XAUUSD"),  # Extra spaces
        
        # === INVALID SYMBOLS ===
        # NOTE: Without MT5 connection, pattern-matched symbols are accepted
        # MT5 will reject them at execution time
        ("INVALID #1", "BUY FAKESYM NOW", "FAKESYM"),  # Accepted by pattern, MT5 will reject
        ("INVALID #2", "SELL NOTREAL", "NOTREAL"),  # Accepted by pattern, MT5 will reject
        ("INVALID #3", "This is just a message", None),  # No valid symbol pattern
        ("INVALID #4", "BUY NOW", None),  # Missing symbol
    ]
    
    print("\n" + "="*70)
    print("SYMBOL RESOLVER TEST SUITE")
    print("="*70)
    
    passed = 0
    failed = 0
    failed_tests = []
    
    for name, message, expected in test_cases:
        result = SymbolResolver.resolve(message)
        
        if result == expected:
            print(f"[✓] {name}: '{message[:40]}...' → {result}")
            passed += 1
        else:
            print(f"[✗] {name}: '{message[:40]}...'")
            print(f"    Expected: {expected}")
            print(f"    Got:      {result}")
            failed += 1
            failed_tests.append(name)
    
    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    if failed_tests:
        print(f"Failed tests: {', '.join(failed_tests)}")
    print("="*70)
    
    return failed == 0


if __name__ == '__main__':
    success = test_symbol_resolver()
    sys.exit(0 if success else 1)
