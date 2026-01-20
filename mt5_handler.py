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
    
    # === CONNECTION HEALTH CHECK ===
    
    def _check_connection_health(self) -> bool:
        """
        Verify MT5 connection is alive and functional.
        
        Checks:
        1. account_info() returns data (proves we're logged in)
        2. symbols_total() > 0 (proves symbols are loaded)
        
        Returns:
            True if connection is healthy, False if dead/degraded
        """
        try:
            account_info = mt5.account_info()
            if account_info is None:
                logger.warning("MT5 health check: account_info() returned None - connection lost")
                return False
            
            symbols_count = mt5.symbols_total()
            if symbols_count == 0:
                logger.warning(f"MT5 health check: 0 symbols available - connection degraded")
                return False
            
            logger.debug(f"MT5 health check: OK ({symbols_count} symbols, balance: {account_info.balance})")
            return True
            
        except Exception as e:
            logger.error(f"MT5 health check failed with exception: {e}")
            return False
    
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
            # === STEP 1: Verify MT5 connection is alive ===
            if not self._check_connection_health():
                logger.warning("MT5 connection dead - attempting reconnect...")
                self.initialized = False
                
                if not self._initialize_sync():
                    return {'success': False, 'error': 'MT5 connection lost and reconnect failed'}
                
                logger.info("MT5 reconnected successfully")
            
            # === STEP 2: Validate symbol ===
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                # Provide more diagnostic info in error
                symbols_count = mt5.symbols_total()
                return {'success': False, 'error': f'Symbol {symbol} not found on broker ({symbols_count} symbols available)'}
            
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
    
    # === LIMIT ORDER EXECUTION ===
    
    def _validate_limit_order_sltp(self, symbol: str, action: str, entry_price: float,
                                    sl: Optional[float], tp: Optional[float]) -> Dict[str, Any]:
        """
        Validate SL/TP positioning for limit orders.
        
        CRITICAL RULES from ai_docs/mt5_limit_orders_api.md:
        - BUY LIMIT: SL < Entry < TP
        - SELL LIMIT: TP < Entry < SL
        - Stops must respect minimum distance from entry
        
        Args:
            symbol: Trading symbol
            action: BUY or SELL
            entry_price: Limit order entry price
            sl: Stop loss price
            tp: Take profit price
            
        Returns:
            dict with 'valid' bool and 'error' if invalid
        """
        try:
            # Get symbol info for stops_level
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return {'valid': False, 'error': f'Symbol {symbol} not found'}
            
            # Calculate minimum stop distance
            # CRITICAL: Even if stops_level = 0, add buffer for safety
            # NOTE: MT5 Python API uses 'trade_stops_level' not 'stops_level'
            point = symbol_info.point
            stops_level = symbol_info.trade_stops_level
            min_distance = max(stops_level, 10) * point * 1.5  # 50% buffer
            
            if action == 'BUY':
                # BUY LIMIT: SL < Entry < TP
                if sl is not None:
                    if sl >= entry_price:
                        return {'valid': False, 'error': f'BUY LIMIT: SL ({sl}) must be < Entry ({entry_price})'}
                    if abs(entry_price - sl) < min_distance:
                        return {'valid': False, 'error': f'SL too close to entry (min distance: {min_distance / point:.0f} points)'}
                
                if tp is not None:
                    if tp <= entry_price:
                        return {'valid': False, 'error': f'BUY LIMIT: TP ({tp}) must be > Entry ({entry_price})'}
                    if abs(tp - entry_price) < min_distance:
                        return {'valid': False, 'error': f'TP too close to entry (min distance: {min_distance / point:.0f} points)'}
            
            elif action == 'SELL':
                # SELL LIMIT: TP < Entry < SL
                if sl is not None:
                    if sl <= entry_price:
                        return {'valid': False, 'error': f'SELL LIMIT: SL ({sl}) must be > Entry ({entry_price})'}
                    if abs(sl - entry_price) < min_distance:
                        return {'valid': False, 'error': f'SL too close to entry (min distance: {min_distance / point:.0f} points)'}
                
                if tp is not None:
                    if tp >= entry_price:
                        return {'valid': False, 'error': f'SELL LIMIT: TP ({tp}) must be < Entry ({entry_price})'}
                    if abs(entry_price - tp) < min_distance:
                        return {'valid': False, 'error': f'TP too close to entry (min distance: {min_distance / point:.0f} points)'}
            
            return {'valid': True}
            
        except Exception as e:
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    def _place_limit_order_sync(self, action: str, symbol: str, volume: float,
                                 entry_price: float, sl: Optional[float],
                                 tp: Optional[float]) -> Dict[str, Any]:
        """
        Place LIMIT order on MT5 (sync).
        
        CRITICAL GOTCHAS from ai_docs/mt5_limit_orders_api.md:
        - All prices MUST be float, not int
        - BUY LIMIT: entry BELOW current Ask
        - SELL LIMIT: entry ABOVE current Bid
        - Use TRADE_ACTION_PENDING + ORDER_TIME_GTC
        """
        try:
            # === STEP 1: Verify MT5 connection is alive ===
            if not self._check_connection_health():
                logger.warning("MT5 connection dead - attempting reconnect...")
                self.initialized = False
                
                if not self._initialize_sync():
                    return {'success': False, 'error': 'MT5 connection lost and reconnect failed'}
                
                logger.info("MT5 reconnected successfully")
            
            # === STEP 2: Validate symbol ===
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                symbols_count = mt5.symbols_total()
                return {'success': False, 'error': f'Symbol {symbol} not found on broker ({symbols_count} symbols available)'}
            
            if not symbol_info.visible:
                mt5.symbol_select(symbol, True)
            
            # === STEP 3: Validate SL/TP positioning ===
            validation = self._validate_limit_order_sltp(symbol, action, entry_price, sl, tp)
            if not validation['valid']:
                return {'success': False, 'error': validation['error']}
            
            # === STEP 4: Determine order type constant ===
            if action == 'BUY':
                order_type = mt5.ORDER_TYPE_BUY_LIMIT
            else:  # SELL
                order_type = mt5.ORDER_TYPE_SELL_LIMIT
            
            # === STEP 5: Build request with all float values ===
            # CRITICAL: All prices MUST be float for MT5
            request = {
                'action': mt5.TRADE_ACTION_PENDING,  # CRITICAL: Use PENDING for limit orders
                'symbol': symbol,
                'volume': float(volume),  # CRITICAL: Must be float
                'type': order_type,
                'price': float(entry_price),  # CRITICAL: Must be float
                'sl': float(sl) if sl else 0.0,  # CRITICAL: Must be float
                'tp': float(tp) if tp else 0.0,  # CRITICAL: Must be float
                'deviation': config.MAX_SLIPPAGE,
                'magic': config.MAGIC_NUMBER,
                'comment': 'telegram_bot_limit',
                'type_time': mt5.ORDER_TIME_GTC,  # CRITICAL: GTC for persistent orders
                'type_filling': mt5.ORDER_FILLING_RETURN,
            }
            
            # === STEP 6: Pre-validate with order_check ===
            check_result = mt5.order_check(request)
            if check_result is None:
                return {'success': False, 'error': f'order_check failed: {mt5.last_error()}'}
            
            if check_result.retcode != 0:
                logger.warning(f"Order check warning: {check_result.retcode} - {check_result.comment}")
            
            # === STEP 7: Send order ===
            result = mt5.order_send(request)
            
            if not result:
                return {'success': False, 'error': f'Send failed: {mt5.last_error()}'}
            
            # === STEP 8: Check success ===
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                errors = {
                    10004: 'Requote', 10006: 'Rejected', 10016: 'Invalid SL/TP',
                    10018: 'Market closed', 10019: 'No funds', 10027: 'Autotrading disabled'
                }
                return {'success': False, 'error': errors.get(result.retcode, result.comment)}
            
            # SUCCESS
            return {
                'success': True,
                'ticket': result.order,
                'price': float(entry_price),
                'volume': result.volume,
                'order_type': 'LIMIT'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def place_limit_order(self, action: str, symbol: str,
                                 entry_price: float, sl: Optional[float] = None,
                                 tp: Optional[float] = None) -> Dict[str, Any]:
        """
        Place limit order (async wrapper).
        
        Args:
            action: BUY or SELL
            symbol: Trading symbol
            entry_price: Limit order entry price
            sl: Stop loss price (optional)
            tp: Take profit price (optional)
            
        Returns:
            dict with 'success', 'ticket', 'price', 'volume', 'order_type'
        """
        if not self.initialized:
            return {'success': False, 'error': 'MT5 not initialized'}
        
        logger.info(f"🔍 Validating LIMIT order: {action} {symbol} @ {entry_price}")
        
        # Pre-validate SL/TP before executor call
        loop = asyncio.get_running_loop()
        validation = await loop.run_in_executor(
            self.executor,
            self._validate_limit_order_sltp,
            symbol, action, entry_price, sl, tp
        )
        
        if not validation['valid']:
            logger.error(f"❌ Limit order validation failed: {validation['error']}")
            return {'success': False, 'error': validation['error']}
        
        logger.info(f"✅ SL/TP validation passed for {action} LIMIT")
        
        # Place the order
        result = await loop.run_in_executor(
            self.executor,
            self._place_limit_order_sync,
            action, symbol, config.LOT_SIZE, entry_price, sl, tp
        )
        
        if result['success']:
            logger.info(f"✅ Limit order placed: {action} {symbol} @ {entry_price} | Ticket: {result['ticket']}")
        else:
            logger.error(f"❌ Limit order failed: {result['error']}")
        
        return result