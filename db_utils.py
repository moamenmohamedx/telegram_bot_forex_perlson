"""
Database Utilities Module
=========================
SQLite database for storing messages, signals, and trade history.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class Database:
    """SQLite database handler for trading bot"""
    
    def __init__(self, db_path: str = 'signals.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self) -> None:
        """Create tables with proper schema"""
        with self.get_connection() as conn:
            # Enable WAL mode for concurrent access
            conn.execute('PRAGMA journal_mode=WAL')
            
            # === TABLE 1: Raw Messages ===
            # Store ALL incoming messages for audit trail
            conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL,
                    telegram_msg_id INTEGER,
                    timestamp TEXT NOT NULL,
                    raw_message TEXT NOT NULL
                )
            ''')
            
            # === TABLE 2: Parsed Signals ===
            # Store parsed trading signals with execution status
            conn.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    action TEXT CHECK(action IN ('BUY', 'SELL')),
                    symbol TEXT NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    status TEXT DEFAULT 'PENDING',
                    mt5_ticket INTEGER,
                    error_message TEXT,
                    FOREIGN KEY (message_id) REFERENCES messages(id)
                )
            ''')
            
            # === INDEXES for Performance ===
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
                ON messages(timestamp DESC)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_telegram_msg_id 
                ON messages(telegram_msg_id)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_signals_timestamp 
                ON signals(timestamp DESC)
            ''')
            
            logger.info("✅ Database initialized successfully")
            
            # Run migrations
            self._migrate_to_limit_orders(conn)
    
    def _migrate_to_limit_orders(self, conn) -> None:
        """
        Add order_type and entry_price columns to signals table for limit order support.
        
        PATTERN: From ai_docs/sqlite_migration_patterns.md
        CRITICAL: Always check column existence before ALTER TABLE
        """
        try:
            # Check existing columns using PRAGMA table_info
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info('signals')")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Add order_type column if missing (default 'MARKET' for existing records)
            if 'order_type' not in columns:
                conn.execute("""
                    ALTER TABLE signals
                    ADD COLUMN order_type TEXT DEFAULT 'MARKET'
                """)
                logger.info("✅ Added order_type column to signals table")
            
            # Add entry_price column if missing (NULL for market orders)
            if 'entry_price' not in columns:
                conn.execute("""
                    ALTER TABLE signals
                    ADD COLUMN entry_price REAL
                """)
                logger.info("✅ Added entry_price column to signals table")
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ Migration to limit orders failed: {e}")
            conn.rollback()
            raise
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # === MESSAGE OPERATIONS ===
    
    def store_message(self, channel_id: int, message_text: str, telegram_msg_id: int) -> int:
        """Store raw message with Telegram message ID and return database ID"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO messages (channel_id, telegram_msg_id, timestamp, raw_message)
                VALUES (?, ?, ?, ?)
            ''', (channel_id, telegram_msg_id, datetime.now().isoformat(), message_text))
            return cursor.lastrowid
    
    # === SIGNAL OPERATIONS ===
    
    def store_signal(self, message_id: int, action: str, symbol: str, 
                     sl: Optional[float] = None, tp: Optional[float] = None,
                     order_type: str = "MARKET", entry_price: Optional[float] = None) -> int:
        """
        Store parsed signal and return its ID.
        
        Args:
            message_id: Database message ID
            action: BUY or SELL
            symbol: Trading symbol (e.g., XAUUSD)
            sl: Stop loss price (optional)
            tp: Take profit price (optional)
            order_type: "MARKET" or "LIMIT" (default: "MARKET")
            entry_price: Entry price for LIMIT orders (optional)
        
        Returns:
            Signal ID
        """
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO signals (message_id, timestamp, action, symbol, stop_loss, take_profit, order_type, entry_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (message_id, datetime.now().isoformat(), action, symbol, sl, tp, order_type, entry_price))
            return cursor.lastrowid
    
    def update_signal_status(self, signal_id: int, status: str, 
                             mt5_ticket: Optional[int] = None, 
                             error_message: Optional[str] = None) -> None:
        """Update signal execution status"""
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE signals
                SET status = ?, mt5_ticket = ?, error_message = ?
                WHERE id = ?
            ''', (status, mt5_ticket, error_message, signal_id))
    
    def get_pending_entry_by_telegram_msg_id(self, telegram_msg_id: int) -> Optional[Dict]:
        """
        Get pending entry signal by Telegram message ID.
        Uses same JOIN pattern to bridge telegram_msg_id → database message_id → signal.
        
        Args:
            telegram_msg_id: Telegram's message ID (from reply_to_msg_id)
        
        Returns:
            Dict with signal_id, action, symbol, status or None
        """
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT s.id, s.action, s.symbol, s.status
                FROM signals s
                JOIN messages m ON s.message_id = m.id
                WHERE m.telegram_msg_id = ?
            ''', (telegram_msg_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'signal_id': row[0],
                    'action': row[1],
                    'symbol': row[2],
                    'status': row[3]
                }
            return None
    
    def update_signal_sltp_by_id(self, signal_id: int,
                                  stop_loss: float, take_profit: float) -> bool:
        """
        Update SL/TP on signal by signal ID.
        
        Args:
            signal_id: Signal database ID
            stop_loss: New stop loss value
            take_profit: New take profit value
            
        Returns:
            True if successful
        """
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE signals
                SET stop_loss = ?, take_profit = ?
                WHERE id = ?
            ''', (stop_loss, take_profit, signal_id))
            return True
    
    # === STATISTICS ===
    
    def get_stats(self) -> Dict[str, Any]:
        """Get trading statistics"""
        with self.get_connection() as conn:
            # Total signals
            total_signals = conn.execute(
                'SELECT COUNT(*) FROM signals'
            ).fetchone()[0]
            
            # Successful trades
            successful = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE status = 'SUCCESS'"
            ).fetchone()[0]
            
            # Failed trades
            failed = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE status = 'ERROR'"
            ).fetchone()[0]
            
            return {
                'total_signals': total_signals,
                'successful_trades': successful,
                'failed_trades': failed
            }

