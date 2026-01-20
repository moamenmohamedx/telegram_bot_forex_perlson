"""
Limit Order Support - Unit Tests
================================
Tests for the limit order implementation following PRP specifications.

Run with: pytest trading_bot/test_limit_orders.py -v
"""

import pytest
import sqlite3
import tempfile
import os
import sys

# Add trading_bot to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser import SignalParser, Signal


class TestLongShortNormalization:
    """Test 1: LONG/SHORT normalization"""
    
    def setup_method(self):
        self.parser = SignalParser()
    
    def test_long_normalizes_to_buy(self):
        """Verify LONG → BUY conversion."""
        signal = self.parser.parse("Long market xau usd Sl - 4462 Tp1 -4401")
        assert signal is not None
        assert signal.action == "BUY", "LONG should normalize to BUY"
    
    def test_short_normalizes_to_sell(self):
        """Verify SHORT → SELL conversion."""
        signal = self.parser.parse("Short market xau usd Sl - 4462 Tp1 -4401")
        assert signal is not None
        assert signal.action == "SELL", "SHORT should normalize to SELL"
    
    def test_case_insensitive_long(self):
        """Verify case-insensitive LONG detection."""
        for text in ["LONG XAUUSD", "long XAUUSD", "Long XAUUSD"]:
            signal = self.parser.parse(f"{text} SL 2650 TP 2700")
            assert signal is not None
            assert signal.action == "BUY", f"'{text}' should normalize to BUY"
    
    def test_case_insensitive_short(self):
        """Verify case-insensitive SHORT detection."""
        for text in ["SHORT XAUUSD", "short XAUUSD", "Short XAUUSD"]:
            signal = self.parser.parse(f"{text} SL 2700 TP 2650")
            assert signal is not None
            assert signal.action == "SELL", f"'{text}' should normalize to SELL"


class TestSpacedSymbolNormalization:
    """Test 2: Spaced symbol normalization"""
    
    def setup_method(self):
        self.parser = SignalParser()
    
    def test_xau_usd_normalization(self):
        """Verify 'xau usd' → 'XAUUSD' normalization."""
        signal = self.parser.parse("Buy xau usd @ 2650 SL 2640 TP 2660")
        assert signal is not None
        assert signal.symbol == "XAUUSD", "Spaced symbols should be normalized"
    
    def test_eur_usd_normalization(self):
        """Verify 'eur usd' → 'EURUSD' normalization."""
        signal = self.parser.parse("Short eur usd market SL 1.10 TP 1.05")
        assert signal is not None
        assert signal.symbol == "EURUSD", "EUR USD should normalize to EURUSD"


class TestLimitOrderDetection:
    """Test 3: LIMIT order type detection"""
    
    def setup_method(self):
        self.parser = SignalParser()
    
    def test_explicit_limit_keyword(self):
        """Verify LIMIT keyword detection."""
        signal = self.parser.parse("XAUUSD Buy Limit 4477, Sl 4473, Tp 4519")
        assert signal is not None
        assert signal.order_type == "LIMIT"
        assert signal.entry_price == 4477.0
    
    def test_at_symbol_detection(self):
        """Verify @ symbol indicates LIMIT order."""
        signal = self.parser.parse("SELL EURUSD @ 1.0950 SL 1.0970 TP 1.0920")
        assert signal is not None
        assert signal.order_type == "LIMIT"
        assert signal.entry_price == 1.0950
    
    def test_at_keyword_detection(self):
        """Verify 'at' keyword indicates LIMIT order."""
        signal = self.parser.parse("BUY EURUSD at 1.0900 SL 1.0850 TP 1.0950")
        assert signal is not None
        assert signal.order_type == "LIMIT"


class TestMarketOrderDetection:
    """Test 4: MARKET order type detection"""
    
    def setup_method(self):
        self.parser = SignalParser()
    
    def test_explicit_market_keyword(self):
        """Verify MARKET keyword detection."""
        signal = self.parser.parse("Buy EURUSD MARKET SL 1.0850 TP 1.0950")
        assert signal is not None
        assert signal.order_type == "MARKET"
        assert signal.entry_price is None
    
    def test_now_keyword_detection(self):
        """Verify NOW keyword indicates MARKET order."""
        signal = self.parser.parse("SELL XAUUSD NOW SL 2660 TP 2640")
        assert signal is not None
        assert signal.order_type == "MARKET"
    
    def test_default_to_market(self):
        """Verify default to MARKET when no entry price keywords."""
        signal = self.parser.parse("BUY XAUUSD SL 2640 TP 2660")
        assert signal is not None
        assert signal.order_type == "MARKET"


class TestMultiTPParsing:
    """Test 5: Multi-TP parsing (use TP1 only)"""
    
    def setup_method(self):
        self.parser = SignalParser()
    
    def test_use_tp1_only(self):
        """Verify TP1, TP2, TP3 extraction with TP1 prioritization."""
        signal = self.parser.parse("SELL XAUUSD @ 2655 SL 2665 TP1 2645 TP2 2640 TP3 2635")
        assert signal is not None
        assert signal.take_profit == 2645.0, "Should use TP1 value only"
    
    def test_multi_tp_with_market_order(self):
        """Verify multi-TP works with MARKET orders."""
        signal = self.parser.parse("Short market xau usd Sl - 4462 Tp1 -4401 Tp2 -4243")
        assert signal is not None
        assert signal.take_profit == 4401.0, "Should use TP1 value (4401)"


class TestBuyLimitValidation:
    """Test 6: BUY LIMIT SL/TP validation"""
    
    def test_valid_buy_limit(self):
        """Verify valid BUY LIMIT: SL < Entry < TP."""
        # Should not raise error
        signal = Signal(
            action="BUY",
            symbol="EURUSD",
            stop_loss=1.0850,
            take_profit=1.0950,
            order_type="LIMIT",
            entry_price=1.0900
        )
        assert signal.order_type == "LIMIT"
    
    def test_invalid_buy_limit_sl_above_entry(self):
        """Verify BUY LIMIT rejects SL >= Entry."""
        with pytest.raises(ValueError, match="SL.*must be < Entry"):
            Signal(
                action="BUY",
                symbol="EURUSD",
                stop_loss=1.0950,  # WRONG: SL > Entry
                take_profit=1.1000,
                order_type="LIMIT",
                entry_price=1.0900
            )
    
    def test_invalid_buy_limit_tp_below_entry(self):
        """Verify BUY LIMIT rejects TP <= Entry."""
        with pytest.raises(ValueError, match="TP.*must be > Entry"):
            Signal(
                action="BUY",
                symbol="EURUSD",
                stop_loss=1.0850,
                take_profit=1.0880,  # WRONG: TP < Entry
                order_type="LIMIT",
                entry_price=1.0900
            )


class TestSellLimitValidation:
    """Test 7: SELL LIMIT SL/TP validation"""
    
    def test_valid_sell_limit(self):
        """Verify valid SELL LIMIT: TP < Entry < SL."""
        # Should not raise error
        signal = Signal(
            action="SELL",
            symbol="XAUUSD",
            stop_loss=2665.0,
            take_profit=2645.0,
            order_type="LIMIT",
            entry_price=2655.0
        )
        assert signal.order_type == "LIMIT"
    
    def test_invalid_sell_limit_sl_below_entry(self):
        """Verify SELL LIMIT rejects SL <= Entry."""
        with pytest.raises(ValueError, match="SL.*must be > Entry"):
            Signal(
                action="SELL",
                symbol="XAUUSD",
                stop_loss=2650.0,  # WRONG: SL < Entry
                take_profit=2640.0,
                order_type="LIMIT",
                entry_price=2655.0
            )
    
    def test_invalid_sell_limit_tp_above_entry(self):
        """Verify SELL LIMIT rejects TP >= Entry."""
        with pytest.raises(ValueError, match="TP.*must be < Entry"):
            Signal(
                action="SELL",
                symbol="XAUUSD",
                stop_loss=2665.0,
                take_profit=2660.0,  # WRONG: TP > Entry
                order_type="LIMIT",
                entry_price=2655.0
            )


class TestDatabaseMigration:
    """Test 8: Database migration"""
    
    def test_order_type_column_added(self):
        """Verify order_type column is added by migration."""
        # Create temporary database
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            # Create database with old schema
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE signals (
                    id INTEGER PRIMARY KEY,
                    message_id INTEGER,
                    timestamp TEXT,
                    action TEXT,
                    symbol TEXT,
                    stop_loss REAL,
                    take_profit REAL,
                    status TEXT,
                    mt5_ticket INTEGER,
                    error_message TEXT
                )
            """)
            # Create messages table for foreign key
            conn.execute("""
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    telegram_msg_id INTEGER,
                    timestamp TEXT,
                    raw_message TEXT
                )
            """)
            conn.commit()
            
            # Import and initialize Database (should run migration)
            from db_utils import Database
            db = Database(db_path)
            
            # Check columns exist
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info('signals')")
            columns = [row[1] for row in cursor.fetchall()]
            
            assert 'order_type' in columns, "order_type column should be added"
            assert 'entry_price' in columns, "entry_price column should be added"
            
            conn.close()
        finally:
            os.unlink(db_path)


class TestBackwardsCompatibility:
    """Test 9: Backwards compatibility - existing signals"""
    
    def setup_method(self):
        self.parser = SignalParser()
    
    def test_blue_max_format(self):
        """Verify Blue Max Forex Academy format still works."""
        signal = self.parser.parse("""
            Buy XAUUSD .. Gold now !
            Stop loss : 4014.427
            Take profit : 4055.964
        """)
        assert signal is not None
        assert signal.action == "BUY"
        assert signal.order_type == "MARKET"  # Should default to MARKET
        assert signal.entry_price is None
        assert abs(signal.stop_loss - 4014.427) < 0.01
        assert abs(signal.take_profit - 4055.964) < 0.01
    
    def test_cobalt_smc_format(self):
        """Verify Cobalt SMC format still works."""
        signal = self.parser.parse("""
            SELL GOLD NOW
            SL - 4,232.37
            TP - 4,205.58
        """)
        assert signal is not None
        assert signal.action == "SELL"
        assert signal.order_type == "MARKET"
        assert abs(signal.stop_loss - 4232.37) < 0.01
        assert abs(signal.take_profit - 4205.58) < 0.01


class TestEntryPriceFloatConversion:
    """Test 10: Entry price float conversion"""
    
    def setup_method(self):
        self.parser = SignalParser()
    
    def test_entry_price_is_float(self):
        """Verify entry prices are always float, never int."""
        signal = self.parser.parse("BUY EURUSD @ 1 SL 0.99 TP 1.01")
        
        # CRITICAL: Must be float for MT5
        if signal and signal.entry_price is not None:
            assert isinstance(signal.entry_price, float), "entry_price must be float"


class TestCopyBotPuneetScenarios:
    """Test the specific Copy Bot Puneet signal scenarios from the PRP"""
    
    def setup_method(self):
        self.parser = SignalParser()
    
    def test_scenario1_short_market(self):
        """Scenario 1: SHORT + MARKET"""
        signal = self.parser.parse("Short market xau usd Sl - 4462 Tp1 -4401 Tp2 -4243")
        
        assert signal is not None
        assert signal.action == "SELL", "SHORT should → SELL"
        assert signal.order_type == "MARKET"
        assert signal.symbol == "XAUUSD"
        assert signal.stop_loss == 4462.0
        assert signal.take_profit == 4401.0  # TP1 only
    
    def test_scenario2_long_market(self):
        """Scenario 2: LONG + MARKET"""
        signal = self.parser.parse("XAGUSD LONG market Sl 75.4 Tp - 78.921")
        
        assert signal is not None
        assert signal.action == "BUY", "LONG should → BUY"
        assert signal.order_type == "MARKET"
        assert signal.symbol == "XAGUSD"
        assert abs(signal.stop_loss - 75.4) < 0.01
        assert abs(signal.take_profit - 78.921) < 0.01
    
    def test_scenario3_buy_limit(self):
        """Scenario 3: BUY LIMIT"""
        signal = self.parser.parse("XAUUSD Buy Limit 4477 , Sl 4473 , Tp 4519")
        
        assert signal is not None
        assert signal.action == "BUY"
        assert signal.order_type == "LIMIT"
        assert signal.entry_price == 4477.0
        assert signal.symbol == "XAUUSD"
        assert signal.stop_loss == 4473.0
        assert signal.take_profit == 4519.0
        
        # Validate SL/TP positioning: SL < Entry < TP
        assert signal.stop_loss < signal.entry_price < signal.take_profit


# === Run tests directly ===
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
