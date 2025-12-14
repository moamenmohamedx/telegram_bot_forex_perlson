"""
Telegram-to-MT5 Trading Signal Bot
===================================
Monitors Telegram channels for trading signals and executes them on MT5.
Handle_message is the core Execution work flow of the app 
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
                # TP/SL parameters - check if this is a reply to a pending entry
                if event.message.reply_to_msg_id:
                    if not config.TRADING_ENABLED:
                        logger.info("⚠️ DRY-RUN mode - Would execute pending entry with TP={signal.take_profit} SL={signal.stop_loss}")
                        # No reply - monitoring privately
                        return
                    
                    if not self.mt5.initialized:
                        logger.warning("⚠️ MT5 offline - Cannot execute pending entry")
                        # No reply - monitoring privately
                        return
                    
                    await self._handle_params_reply(signal, event)
                else:
                    logger.warning("PARAMS_ONLY signal without reply chain - ignoring")
                    logger.warning("   TIP: Reply to an entry signal with TP/SL to execute")
            
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
    
    async def _handle_entry_signal(self, signal, message_id: int, event) -> None:
        """Store entry signal as pending, wait for TP/SL reply before execution"""
        # CRITICAL: NO mt5.place_order() here - just store pending
        
        logger.info(f"📋 Entry signal queued: {signal.action} {signal.symbol} (waiting for TP/SL)")
        
        # Store signal with PENDING_ENTRY status
        signal_id = self.db.store_signal(
            message_id, signal.action, signal.symbol, None, None
        )
        self.db.update_signal_status(signal_id, 'PENDING_ENTRY')
        
        logger.info(f"📋 Stored pending entry #{signal_id}: {signal.action} {signal.symbol}")
        # No reply - monitoring privately
    
    async def _handle_params_reply(self, signal, event) -> None:
        """Execute pending entry when TP/SL reply arrives"""
        reply_to_id = event.message.reply_to_msg_id
        
        if not reply_to_id:
            logger.warning("PARAMS_ONLY signal without reply chain - cannot match pending entry")
            return
        
        # === STEP 1: Validate BOTH TP and SL present ===
        if signal.stop_loss is None or signal.take_profit is None:
            logger.warning(f"⚠️ Reply missing TP or SL: tp={signal.take_profit}, sl={signal.stop_loss}")
            # No reply - monitoring privately
            return
        
        logger.info(f"🔍 Looking up pending entry for Telegram message ID: {reply_to_id}")
        
        # === STEP 2: Lookup pending entry ===
        pending = self.db.get_pending_entry_by_telegram_msg_id(reply_to_id)
        
        if not pending:
            logger.warning(f"⚠️ No pending entry found for message_id {reply_to_id}")
            # No reply - monitoring privately
            return
        
        # === STEP 3: Check if already executed (duplicate reply) ===
        if pending['status'] != 'PENDING_ENTRY':
            logger.warning(f"⚠️ Signal {pending['signal_id']} already processed (status: {pending['status']})")
            # No reply - monitoring privately
            return
        
        # === STEP 4: Execute trade with full parameters ===
        logger.info(f"🚀 Executing: {pending['action']} {pending['symbol']} TP={signal.take_profit} SL={signal.stop_loss}")
        
        result = await self.mt5.place_order(
            action=pending['action'],
            symbol=pending['symbol'],
            sl=signal.stop_loss,
            tp=signal.take_profit
        )
        
        # === STEP 5: Update database and respond ===
        if result['success']:
            ticket_id = result['ticket']
            
            # Update signal with execution details
            self.db.update_signal_status(pending['signal_id'], 'SUCCESS', ticket_id)
            self.db.update_signal_sltp_by_id(pending['signal_id'], signal.stop_loss, signal.take_profit)
            
            # Store position
            self.db.store_position(
                pending['signal_id'], pending['symbol'], ticket_id,
                pending['action'], result['price'], result['volume']
            )
            
            logger.info(f"✅ Executed {pending['action']} {pending['symbol']} @ {result['price']} | TP: {signal.take_profit} | SL: {signal.stop_loss} | Ticket: #{ticket_id}")
            # No reply - monitoring privately
        else:
            logger.error(f"❌ Failed to execute pending entry: {result['error']}")
            self.db.update_signal_status(pending['signal_id'], 'ERROR', error_message=result['error'])
            # No reply - monitoring privately
    
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
