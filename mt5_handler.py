"""
MetaTrader 5 Handler
====================
Handles MT5 communication with async wrappers.
"""

import MetaTrader5 as mt5
import logging
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
import asyncio

import config

logger = logging.getLogger(__name__)


class MT5Handler:
    """Async wrapper for MetaTrader 5"""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.initialized = False
        self._symbol_cache = {}  # Cache for validated symbols
    
    # === INITIALIZATION ===
    
    def _initialize_sync(self) -> bool:
        """Initialize MT5 (sync)"""
        try:
            logger.info(f"Attempting MT5 connection...")
            logger.info(f"  Path: {config.MT5_PATH}")
            logger.info(f"  Login: {config.MT5_LOGIN}")
            logger.info(f"  Server: {config.MT5_SERVER}")

            if not mt5.initialize(
                path=config.MT5_PATH,
                login=config.MT5_LOGIN,
                password=config.MT5_PASSWORD,
                server=config.MT5_SERVER,
                timeout=60000
            ):
                error = mt5.last_error()
                logger.error(f"❌ MT5 init failed!")
                logger.error(f"   Error code: {error[0] if error else 'Unknown'}")
                logger.error(f"   Error message: {error[1] if error and len(error) > 1 else 'Unknown'}")
                logger.error(f"   Possible fixes:")
                logger.error(f"   1. Check MT5 is installed at: {config.MT5_PATH}")
                logger.error(f"   2. Verify login credentials in .env")
                logger.error(f"   3. Check server name is correct: {config.MT5_SERVER}")
                logger.error(f"   4. Enable 'Algo Trading' in MT5")
                return False

            account = mt5.account_info()
            if account:
                logger.info(f"✅ MT5 Account: {account.login} | Balance: {account.balance}")

            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"❌ MT5 exception: {e}", exc_info=True)
            return False
    
    async def initialize(self) -> bool:
        """Initialize MT5 (async)"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._initialize_sync)
    
    def _shutdown_sync(self) -> None:
        """Shutdown MT5 (sync)"""
        mt5.shutdown()
        self.initialized = False
    
    async def shutdown(self) -> None:
        """Shutdown MT5 (async)"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, self._shutdown_sync)
    
    # === SYMBOL VALIDATION ===
    
    def _validate_symbol_sync(self, symbol: str) -> Dict[str, Any]:
        """
        Validate symbol exists on broker (sync).
        
        Returns:
            dict with 'valid' bool, 'symbol' str, 'error' str, 'digits' int
        """
        try:
            # Check cache first
            if symbol in self._symbol_cache:
                return self._symbol_cache[symbol]
            
            # Query MT5 for symbol info
            info = mt5.symbol_info(symbol)
            
            if info is None:
                result = {'valid': False, 'error': f'Symbol {symbol} not found on broker'}
            elif not info.visible:
                # Try to make symbol visible in MarketWatch
                if not mt5.symbol_select(symbol, True):
                    result = {'valid': False, 'error': f'Symbol {symbol} not available for trading'}
                else:
                    result = {'valid': True, 'symbol': symbol, 'digits': info.digits}
            else:
                result = {'valid': True, 'symbol': symbol, 'digits': info.digits}
            
            # Cache result for performance
            self._symbol_cache[symbol] = result
            return result
            
        except Exception as e:
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    async def validate_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Validate symbol (async wrapper).
        
        Args:
            symbol: MT5 symbol to validate (e.g., XAUUSD, EURUSD)
            
        Returns:
            dict with 'valid' bool, 'symbol' str, 'error' str (if invalid)
        """
        if not self.initialized:
            # Fallback: accept pattern-matched symbols when MT5 offline
            logger.debug(f"MT5 not initialized - accepting symbol {symbol} (will validate at execution)")
            return {'valid': True, 'symbol': symbol, 'offline_mode': True}
        
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._validate_symbol_sync, symbol)
    
    # === ORDER EXECUTION ===
    
    def _place_order_sync(self, action: str, symbol: str,
                          sl: Optional[float], tp: Optional[float]) -> Dict[str, Any]:
        """Place market order (sync)"""
        try:
            # Validate symbol
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return {'success': False, 'error': f'Symbol {symbol} not found'}
            
            if not symbol_info.visible:
                mt5.symbol_select(symbol, True)
            
            # Get price
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return {'success': False, 'error': f'No tick for {symbol}'}
            
            # Order type and price
            if action == 'BUY':
                order_type = mt5.ORDER_TYPE_BUY
                price = tick.ask
            else:
                order_type = mt5.ORDER_TYPE_SELL
                price = tick.bid
            
            # Build request
            request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': symbol,
                'volume': config.LOT_SIZE,
                'type': order_type,
                'price': price,
                'sl': sl or 0.0,
                'tp': tp or 0.0,
                'deviation': config.MAX_SLIPPAGE,
                'magic': config.MAGIC_NUMBER,
                'comment': 'telegram_bot',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC,
            }
            
            # Check order
            check = mt5.order_check(request)
            if not check or check.retcode != 0:
                return {'success': False, 'error': f'Check failed: {check.comment if check else "None"}'}
            
            # Send order
            result = mt5.order_send(request)
            if not result:
                return {'success': False, 'error': f'Send failed: {mt5.last_error()}'}
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                errors = {
                    10004: 'Requote', 10006: 'Rejected', 10016: 'Invalid SL/TP',
                    10018: 'Market closed', 10019: 'No funds', 10027: 'Autotrading disabled'
                }
                return {'success': False, 'error': errors.get(result.retcode, result.comment)}
            
            return {'success': True, 'ticket': result.order, 'price': result.price, 'volume': result.volume}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def place_order(self, action: str, symbol: str,
                          sl: Optional[float] = None, tp: Optional[float] = None) -> Dict[str, Any]:
        """Place order (async)"""
        if not self.initialized:
            return {'success': False, 'error': 'MT5 not initialized'}
        
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._place_order_sync, action, symbol, sl, tp)
