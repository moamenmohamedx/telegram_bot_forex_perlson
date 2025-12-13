"""
Database Clearing Utility
==========================
Safely clear all data from SQLite database while preserving schema.

Usage:
    python clear_database.py [--db-path signals.db] [--confirm] [--drop-tables]
"""

import sqlite3
import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, Any
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DatabaseClearer:
    """SQLite database clearing utility with transaction safety and foreign key handling"""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        logger.info(f"📁 Database: {self.db_path.absolute()}")
    
    @contextmanager
    def get_connection(self):
        """Context manager with automatic rollback on errors"""
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def get_tables(self, conn: sqlite3.Connection) -> list:
        """Get all user tables (excludes system tables)"""
        cursor = conn.execute('''
            SELECT name FROM sqlite_master 
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        ''')
        return [row[0] for row in cursor.fetchall()]
    
    def get_row_counts(self, conn: sqlite3.Connection) -> Dict[str, int]:
        """Get row counts for all tables"""
        counts = {}
        for table in self.get_tables(conn):
            cursor = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
            counts[table] = cursor.fetchone()[0]
        return counts
    
    def clear_all_data(self, preserve_schema: bool = True) -> Dict[str, Any]:
        """
        Clear all data from database.
        
        Args:
            preserve_schema: If True, preserve tables/indexes. If False, drop all tables.
            
        Returns:
            Dict with operation results
        """
        with self.get_connection() as conn:
            # === STEP 1: Get initial state ===
            initial_counts = self.get_row_counts(conn)
            total_rows = sum(initial_counts.values())
            
            logger.info(f"📊 Initial state: {total_rows} total rows across {len(initial_counts)} tables")
            for table, count in initial_counts.items():
                if count > 0:
                    logger.info(f"   {table}: {count} rows")
            
            if total_rows == 0:
                logger.info("✅ Database is already empty")
                return {'success': True, 'tables_cleared': 0, 'rows_deleted': 0}
            
            # === STEP 2: Disable foreign keys ===
            conn.execute('PRAGMA foreign_keys = OFF')
            logger.info("🔓 Foreign key constraints disabled")
            
            try:
                tables = self.get_tables(conn)
                rows_deleted = 0
                
                if preserve_schema:
                    # === STEP 3: Delete data (preserve schema) ===
                    logger.info(f"🗑️  Deleting data from {len(tables)} tables...")
                    for table in tables:
                        cursor = conn.execute(f'DELETE FROM "{table}"')
                        deleted = cursor.rowcount
                        rows_deleted += deleted
                        if deleted > 0:
                            logger.info(f"   ✓ {table}: {deleted} rows deleted")
                    
                    # Reset auto-increment counters
                    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
                    if cursor.fetchone():
                        for table in tables:
                            conn.execute(f'DELETE FROM sqlite_sequence WHERE name = "{table}"')
                    logger.info("🔄 Auto-increment counters reset")
                else:
                    # === STEP 3: Drop all tables ===
                    logger.warning(f"⚠️  DROPPING {len(tables)} tables (destructive mode)")
                    for table in tables:
                        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
                        logger.info(f"   ✓ Dropped: {table}")
                    rows_deleted = total_rows
                
                # === STEP 4: Re-enable foreign keys ===
                conn.execute('PRAGMA foreign_keys = ON')
                logger.info("🔒 Foreign key constraints re-enabled")
                
                # === STEP 5: Verify ===
                final_counts = self.get_row_counts(conn)
                final_total = sum(final_counts.values())
                
                if final_total > 0:
                    logger.warning(f"⚠️  Warning: {final_total} rows still remain")
                else:
                    logger.info("✅ Verification: All data cleared successfully")
                
                return {
                    'success': True,
                    'tables_cleared': len(tables),
                    'rows_deleted': rows_deleted
                }
                
            except Exception as e:
                # Always re-enable foreign keys on error
                try:
                    conn.execute('PRAGMA foreign_keys = ON')
                except:
                    pass
                logger.error(f"❌ Error during deletion: {e}", exc_info=True)
                raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Clear all data from SQLite database while preserving schema',
        epilog='Examples:\n  python clear_database.py --confirm\n  python clear_database.py --db-path custom.db --confirm --drop-tables'
    )
    parser.add_argument('--db-path', type=str, default='signals.db', help='Database file path')
    parser.add_argument('--confirm', action='store_true', help='Confirm deletion (required)')
    parser.add_argument('--drop-tables', action='store_true', help='Drop all tables (DESTRUCTIVE)')
    
    args = parser.parse_args()
    
    try:
        clearer = DatabaseClearer(args.db_path)
        
        # Show preview
        with clearer.get_connection() as conn:
            counts = clearer.get_row_counts(conn)
            total = sum(counts.values())
            
            if total == 0:
                logger.info("✅ Database is already empty")
                return 0
            
            logger.info("")
            logger.info("="*60)
            logger.info("DATABASE CLEARING OPERATION")
            logger.info("="*60)
            logger.info(f"Database: {args.db_path}")
            logger.info(f"Total rows: {total}")
            logger.info(f"Mode: {'DROP TABLES' if args.drop_tables else 'CLEAR DATA'}")
            logger.info("="*60)
        
        # Require confirmation
        if not args.confirm:
            logger.warning("⚠️  DRY-RUN MODE - No data will be deleted")
            logger.warning(f"   Use: python clear_database.py --db-path {args.db_path} --confirm")
            return 0
        
        # Perform clearing
        logger.info("🚀 Starting operation...")
        result = clearer.clear_all_data(preserve_schema=not args.drop_tables)
        
        # Summary
        logger.info("")
        logger.info("="*60)
        logger.info("OPERATION COMPLETE")
        logger.info("="*60)
        logger.info(f"✅ Success: {result['success']}")
        logger.info(f"📊 Tables: {result['tables_cleared']}")
        logger.info(f"🗑️  Rows deleted: {result['rows_deleted']}")
        logger.info("="*60)
        
        return 0
        
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return 1
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
