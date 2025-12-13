"""
Telegram-to-MT5 Trading Signal Bot
===================================
Monitors Telegram channels for trading signals and executes them on MT5.

Usage:
    python main.py
"""

import asyncio
import logging
import sys
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
import backoff

import config
from parser import SignalParser
from mt5_handler import MT5Handler
from db_utils import Database

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger('telethon').setLevel(logging.WARNING)


class TradingBot:
    """Main trading bot class"""
    
    def __init__(self):
        # Initialize Telegram client
        self.client = TelegramClient(
            'bot_session',
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH
        )
        
        # Initialize components
        self.parser = SignalParser()
        self.mt5 = MT5Handler()
        self.db = Database()
    
    async def start(self) -> None:
        """Initialize all services and start monitoring"""
        logger.info("="*50)
        logger.info("Starting Telegram-to-MT5 Trading Bot")
        logger.info("="*50)
        
        # Validate config
        if not config.validate_config():
            raise RuntimeError("Configuration validation failed")
        
        # Connect to Telegram
        logger.info("Connecting to Telegram...")
        await self.client.start(phone=config.TELEGRAM_PHONE)
        me = await self.client.get_me()
        logger.info(f"Connected as: {me.first_name} ({me.phone})")
        
        # Verify channel access
        await self._verify_channels()
        
        # Initialize MT5 (optional - continue without it for testing)
        logger.info("Initializing MetaTrader 5...")
        if await self.mt5.initialize():
            logger.info("MT5 initialized successfully")
        else:
            logger.warning("⚠️ MT5 failed to initialize - running in TELEGRAM-ONLY mode")
            logger.warning("   Signals will be logged but NOT executed")
        
        # Register message handler
        @self.client.on(events.NewMessage(chats=config.TELEGRAM_CHANNELS))
        async def message_handler(event):
            await self.handle_message(event)
        
        # Log status
        logger.info("")
        logger.info("="*50)
        logger.info("BOT STATUS")
        logger.info("="*50)
        logger.info(f"   Channels monitored: {config.TELEGRAM_CHANNELS}")
        logger.info(f"   MT5 status: {'READY' if self.mt5.initialized else 'OFFLINE'}")
        logger.info(f"   Mode: {'LIVE TRADING' if config.TRADING_ENABLED else 'DRY-RUN'}")
        logger.info(f"   Lot size: {config.LOT_SIZE}")
        logger.info("="*50)
        logger.info("Listening for signals... (send a message to the channel to test)")
    
    async def _verify_channels(self) -> None:
        """Verify we can access the configured channels"""
        logger.info("")
        logger.info("Verifying channel access...")
        for channel_id in config.TELEGRAM_CHANNELS:
            try:
                entity = await self.client.get_entity(channel_id)
                logger.info(f"✅ Channel {channel_id}: {entity.title} (ID: {entity.id})")
            except ValueError:
                logger.error(f"❌ Channel {channel_id}: NOT FOUND or NO ACCESS")
                logger.error(f"   Make sure you're a member of this channel/group")
            except Exception as e:
                logger.error(f"❌ Channel {channel_id}: Error - {e}")
    
    @backoff.on_exception(backoff.expo, FloodWaitError, max_tries=5)
    async def handle_message(self, event) -> None:
        """Handle incoming Telegram message"""
        try:
            message_text = event.message.text
            if not message_text:
                return
            
            # Store raw message
            message_id = self.db.store_message(
                event.chat_id, 
                message_text,
                event.message.id  # Telegram's message ID
            )
            preview = message_text[:80].replace('\n', ' ')
            logger.info(f"📩 Message #{message_id} from {event.chat_id}: {preview}...")
            logger.debug(f"🔍 Telegram message ID: {event.message.id}, Database ID: {message_id}")
            
            # Quick check
            if not self.parser.is_signal_message(message_text):
                return
            
            # Parse signal
            signal = self.parser.parse(message_text)
            if not signal:
                return
            
            logger.info(f"Signal: {signal}")
            
            # Route based on signal type
            if signal.signal_type == 'COMPLETE':
                # Traditional single-message signal with SL/TP (backward compatible)
                signal_id = self.db.store_signal(
                    message_id, signal.action, signal.symbol,
                    signal.stop_loss, signal.take_profit
                )
                
                # Execute trade if enabled and MT5 is ready
                if not config.TRADING_ENABLED:
                    logger.info("DRY-RUN mode - Trade not executed")
                    self.db.update_signal_status(signal_id, 'DRY-RUN')
                    return
                
                if not self.mt5.initialized:
                    logger.warning("MT5 not initialized - Trade not executed")
                    self.db.update_signal_status(signal_id, 'MT5_OFFLINE')
                    return
                
                if signal.action == 'CLOSE':
                    await self._handle_close_signal(signal, signal_id)
                else:
                    await self._handle_trade_signal(signal, signal_id)
            
            elif signal.signal_type == 'ENTRY_ONLY':
                # Entry signal without SL/TP - execute immediately, wait for params via reply
                if not config.TRADING_ENABLED:
                    logger.info("DRY-RUN mode - Entry signal logged but not executed")
                    signal_id = self.db.store_signal(
                        message_id, signal.action, signal.symbol, None, None
                    )
                    self.db.update_signal_status(signal_id, 'DRY-RUN')
                    return
                
                if not self.mt5.initialized:
                    logger.warning("MT5 not initialized - Entry signal not executed")
                    signal_id = self.db.store_signal(
                        message_id, signal.action, signal.symbol, None, None
                    )
                    self.db.update_signal_status(signal_id, 'MT5_OFFLINE')
                    return
                
                await self._handle_entry_signal(signal, message_id, event)
            
            elif signal.signal_type == 'PARAMS_ONLY':
                # TP/SL parameters - check if this is a reply to an entry signal
                if event.message.reply_to_msg_id:
                    if not config.TRADING_ENABLED:
                        logger.info("DRY-RUN mode - Position modification logged but not executed")
                        await event.reply("⚠️ DRY-RUN mode - Would modify position with SL/TP")
                        return
                    
                    if not self.mt5.initialized:
                        logger.warning("MT5 not initialized - Cannot modify position")
                        await event.reply("⚠️ MT5 offline - Cannot modify position")
                        return
                    
                    await self._handle_params_reply(signal, event)
                else:
                    logger.warning("PARAMS_ONLY signal without reply chain - ignoring")
                    logger.warning("   TIP: Use Telegram REPLY feature for accurate matching")
            
            else:
                logger.debug(f"Invalid signal type: {signal.signal_type}")
                
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
    
    async def _handle_trade_signal(self, signal, signal_id: int) -> None:
        """Execute BUY or SELL trade"""
        logger.info(f"Executing {signal.action} {signal.symbol}...")
        
        result = await self.mt5.place_order(
            action=signal.action,
            symbol=signal.symbol,
            sl=signal.stop_loss,
            tp=signal.take_profit
        )
        
        if result['success']:
            logger.info(f"SUCCESS - Ticket: {result['ticket']} @ {result['price']}")
            self.db.update_signal_status(signal_id, 'SUCCESS', result['ticket'])
            self.db.store_position(
                signal_id, signal.symbol, result['ticket'],
                signal.action, result['price'], result['volume']
            )
        else:
            logger.error(f"FAILED - {result['error']}")
            self.db.update_signal_status(signal_id, 'ERROR', error_message=result['error'])
    
    async def _handle_close_signal(self, signal, signal_id: int) -> None:
        """Close all positions for symbol"""
        logger.info(f"Closing {signal.symbol} positions...")
        
        positions = await self.mt5.get_positions(signal.symbol)
        if not positions:
            logger.warning(f"No open positions for {signal.symbol}")
            self.db.update_signal_status(signal_id, 'NO_POSITIONS')
            return
        
        results = await self.mt5.close_all_positions(signal.symbol)
        success_count = sum(1 for r in results if r.get('success'))
        
        if success_count == len(positions):
            logger.info(f"Closed {success_count} position(s)")
            self.db.update_signal_status(signal_id, 'SUCCESS')
        else:
            logger.warning(f"Closed {success_count}/{len(positions)}")
            self.db.update_signal_status(signal_id, 'PARTIAL')
    
    async def _handle_entry_signal(self, signal, message_id: int, event) -> None:
        """Execute entry signal immediately, store for later TP/SL modification"""
        logger.info(f"📈 Entry signal: {signal.action} {signal.symbol} (no SL/TP)")
        
        # Execute immediately
        result = await self.mt5.place_order(
            action=signal.action,
            symbol=signal.symbol,
            sl=None,  # No SL/TP - will be added later via reply
            tp=None
        )
        
        if result['success']:
            ticket_id = result['ticket']
            
            # Store signal with ticket and special status
            signal_id = self.db.store_signal(
                message_id, signal.action, signal.symbol,
                None, None  # No SL/TP yet
            )
            self.db.update_signal_status(signal_id, 'EXECUTED_NO_SLTP', ticket_id)
            
            # Store position
            self.db.store_position(
                signal_id, signal.symbol, ticket_id,
                signal.action, result['price'], result['volume']
            )
            
            logger.info(f"✅ Opened {signal.action} {signal.symbol} #{ticket_id} (waiting for TP/SL)")
            await event.reply(f"✅ Opened {signal.action} {signal.symbol} #{ticket_id} (waiting for TP/SL)")
        else:
            logger.error(f"❌ Failed to execute: {result['error']}")
            signal_id = self.db.store_signal(
                message_id, signal.action, signal.symbol,
                None, None
            )
            self.db.update_signal_status(signal_id, 'ERROR', error_message=result['error'])
            await event.reply(f"❌ Failed to execute: {result['error']}")
    
    async def _handle_params_reply(self, signal, event) -> None:
        """Modify existing position when TP/SL reply arrives"""
        reply_to_id = event.message.reply_to_msg_id
        
        if not reply_to_id:
            logger.warning("PARAMS_ONLY signal without reply chain - cannot match position")
            return
        
        logger.info(f"🔍 Looking up position for Telegram message ID: {reply_to_id}")
        
        # Lookup original position by Telegram message_id
        position_info = self.db.get_signal_by_telegram_msg_id(reply_to_id)
        
        if not position_info:
            logger.warning(f"No position found for message_id {reply_to_id}")
            await event.reply(f"⚠️ No open position found to modify")
            return
        
        ticket_id = position_info['ticket_id']
        
        # Modify the position
        result = await self.mt5.position_modify(
            ticket_id=ticket_id,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit
        )
        
        if result['success']:
            # Update database
            self.db.update_signal_sltp_by_telegram_id(reply_to_id, signal.stop_loss, signal.take_profit)
            logger.info(f"✅ Set TP={signal.take_profit} SL={signal.stop_loss} on #{ticket_id}")
            await event.reply(f"✅ Set TP={signal.take_profit} SL={signal.stop_loss} on #{ticket_id}")
        else:
            logger.error(f"❌ Failed to modify position: {result['error']}")
            await event.reply(f"❌ Failed to modify position: {result['error']}")
    
    async def stop(self) -> None:
        """Cleanup"""
        logger.info("Shutting down...")
        await self.mt5.shutdown()
        await self.client.disconnect()
        logger.info("Shutdown complete")
    
    async def run(self) -> None:
        """Main loop"""
        try:
            await self.start()
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            pass
        finally:
            await self.stop()


if __name__ == '__main__':
    try:
        asyncio.run(TradingBot().run())
    except KeyboardInterrupt:
        print("\nStopped by user")
