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
    
    # === POSITION MODIFICATION ===
    
    def _position_modify_sync(self, ticket_id: int, stop_loss: Optional[float],
                              take_profit: Optional[float]) -> Dict[str, Any]:
        """Modify SL/TP on existing position using TRADE_ACTION_SLTP (sync)"""
        try:
            # Get position info first
            position = mt5.positions_get(ticket=ticket_id)
            if not position:
                return {'success': False, 'error': f'Position {ticket_id} not found'}
            
            position = position[0]
            
            # Build request for TRADE_ACTION_SLTP
            request = {
                'action': mt5.TRADE_ACTION_SLTP,
                'position': ticket_id,
                'symbol': position.symbol,
                'sl': stop_loss if stop_loss else position.sl,
                'tp': take_profit if take_profit else position.tp,
            }
            
            # Send modification request
            result = mt5.order_send(request)
            
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Modified position {ticket_id}: SL={stop_loss}, TP={take_profit}")
                return {
                    'success': True,
                    'ticket': ticket_id,
                    'message': f'Position {ticket_id} modified successfully'
                }
            else:
                error_msg = f"Failed to modify position: {result.comment}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def position_modify(self, ticket_id: int, stop_loss: Optional[float] = None,
                              take_profit: Optional[float] = None) -> Dict[str, Any]:
        """
        Modify SL/TP on existing position (async).
        
        Args:
            ticket_id: MT5 position ticket ID
            stop_loss: New stop loss value (or None to keep existing)
            take_profit: New take profit value (or None to keep existing)
            
        Returns:
            Dict with success status and message
        """
        if not self.initialized:
            return {'success': False, 'error': 'MT5 not initialized'}
        
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self.executor, self._position_modify_sync, ticket_id, stop_loss, take_profit
        )
