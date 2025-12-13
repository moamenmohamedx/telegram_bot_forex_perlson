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
                    action TEXT CHECK(action IN ('BUY', 'SELL', 'CLOSE')),
                    symbol TEXT NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    status TEXT DEFAULT 'PENDING',
                    mt5_ticket INTEGER,
                    error_message TEXT,
                    FOREIGN KEY (message_id) REFERENCES messages(id)
                )
            ''')
            
            # === TABLE 3: Active Positions ===
            # Track open positions for CLOSE signal handling
            conn.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    mt5_ticket INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    open_price REAL,
                    lot_size REAL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    close_price REAL,
                    pips REAL,
                    status TEXT DEFAULT 'OPEN',
                    FOREIGN KEY (signal_id) REFERENCES signals(id)
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
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_positions_symbol_status 
                ON positions(symbol, status)
            ''')
            
            logger.info("✅ Database initialized successfully")
    
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
                     sl: Optional[float] = None, tp: Optional[float] = None) -> int:
        """Store parsed signal and return its ID"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO signals (message_id, timestamp, action, symbol, stop_loss, take_profit)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (message_id, datetime.now().isoformat(), action, symbol, sl, tp))
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
    
    def get_signal_by_message_id(self, message_id: int) -> Optional[Dict]:
        """
        Lookup signal by Telegram message ID for position modification.
        
        Args:
            message_id: Telegram message ID
            
        Returns:
            Dict with ticket_id, symbol, action, stop_loss, take_profit or None
        """
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT mt5_ticket, symbol, action, stop_loss, take_profit
                FROM signals 
                WHERE message_id = ?
            ''', (message_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'ticket_id': row[0],
                    'symbol': row[1],
                    'action': row[2],
                    'stop_loss': row[3],
                    'take_profit': row[4]
                }
            return None
    
    def get_signal_by_telegram_msg_id(self, telegram_msg_id: int) -> Optional[Dict]:
        """
        Lookup signal by Telegram message ID for position modification.
        Uses JOIN to bridge telegram_msg_id → database message_id → signal.
        
        Args:
            telegram_msg_id: Telegram's internal message ID (from reply_to_msg_id)
            
        Returns:
            Dict with ticket_id, symbol, action, stop_loss, take_profit or None
        """
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT s.mt5_ticket, s.symbol, s.action, s.stop_loss, s.take_profit
                FROM signals s
                JOIN messages m ON s.message_id = m.id
                WHERE m.telegram_msg_id = ?
            ''', (telegram_msg_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'ticket_id': row[0],
                    'symbol': row[1],
                    'action': row[2],
                    'stop_loss': row[3],
                    'take_profit': row[4]
                }
            return None
    
    def update_signal_sltp(self, message_id: int, stop_loss: Optional[float], 
                           take_profit: Optional[float]) -> bool:
        """
        Update SL/TP after position modification.
        
        Args:
            message_id: Telegram message ID
            stop_loss: New stop loss value
            take_profit: New take profit value
            
        Returns:
            True if successful
        """
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE signals 
                SET stop_loss = ?, take_profit = ?, status = 'MODIFIED'
                WHERE message_id = ?
            ''', (stop_loss, take_profit, message_id))
            return True
    
    def update_signal_sltp_by_telegram_id(self, telegram_msg_id: int, 
                                           stop_loss: Optional[float], 
                                           take_profit: Optional[float]) -> bool:
        """
        Update SL/TP after position modification using Telegram message ID.
        
        Args:
            telegram_msg_id: Telegram's internal message ID
            stop_loss: New stop loss value
            take_profit: New take profit value
            
        Returns:
            True if successful
        """
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE signals 
                SET stop_loss = ?, take_profit = ?, status = 'MODIFIED'
                WHERE message_id IN (
                    SELECT id FROM messages WHERE telegram_msg_id = ?
                )
            ''', (stop_loss, take_profit, telegram_msg_id))
            return True
    
    # === POSITION OPERATIONS ===
    
    def store_position(self, signal_id: int, symbol: str, mt5_ticket: int,
                       action: str, open_price: float, lot_size: float) -> int:
        """Store new open position"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO positions (signal_id, symbol, mt5_ticket, action, 
                                       open_price, lot_size, opened_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN')
            ''', (signal_id, symbol, mt5_ticket, action, open_price, lot_size,
                  datetime.now().isoformat()))
            return cursor.lastrowid
    
    def get_open_positions(self, symbol: str) -> list:
        """Get all open positions for a symbol"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM positions
                WHERE symbol = ? AND status = 'OPEN'
                ORDER BY opened_at DESC
            ''', (symbol,))
            return [dict(row) for row in cursor.fetchall()]
    
    def close_position(self, position_id: int, close_price: float, pips: float) -> None:
        """Mark position as closed"""
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE positions
                SET status = 'CLOSED', closed_at = ?, close_price = ?, pips = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), close_price, pips, position_id))
    
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
            
            # Open positions
            open_positions = conn.execute(
                "SELECT COUNT(*) FROM positions WHERE status = 'OPEN'"
            ).fetchone()[0]
            
            return {
                'total_signals': total_signals,
                'successful_trades': successful,
                'failed_trades': failed,
                'open_positions': open_positions
            }

