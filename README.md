# Telegram-to-MT5 Trading Signal Bot

Automated trading bot that monitors Telegram channels for trading signals and executes them on MetaTrader 5.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Production-brightgreen.svg)

## Features

- **Real-time Signal Detection**: Monitors Telegram channels for BUY/SELL signals
- **Smart Parsing**: Extracts action, symbol, stop loss, and take profit from messages
- **Two-Message Signal Support**: Handles entry signals followed by TP/SL replies
- **Symbol Alias Resolution**: Converts aliases (GOLD, BTC, CABLE) to MT5 symbols
- **Dry-Run Mode**: Test signal detection without executing trades
- **Audit Trail**: SQLite database stores all messages and trade history
- **Async Architecture**: Non-blocking Telegram and MT5 operations

## Supported Signal Formats

### Complete Signals (Single Message)
```
Buy XAUUSD .. Gold now !
Stop loss : 4014.427
Take profit : 4055.964
```

### Two-Message Signals
**Message 1 (Entry):**
```
SELL GOLD NOW
```
**Message 2 (Reply with parameters):**
```
TP 2700 SL 2650
```

## Installation

### Prerequisites
- Python 3.9 or higher
- MetaTrader 5 terminal installed
- Telegram account with API access

### Step 1: Clone and Setup Environment
```bash
git clone <repository-url>
cd telegram_bot_forex/trading_bot

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Get Telegram API Credentials
1. Go to [https://my.telegram.org/apps](https://my.telegram.org/apps)
2. Log in with your phone number
3. Create a new application (any name/description)
4. Note your **API ID** and **API Hash**

### Step 3: Get Telegram Channel IDs

Use the included `find_all_groups.py` utility to discover all your Telegram groups and channels:

```bash
cd trading_bot
python find_all_groups.py
```

**What the script does:**
1. Connects to your Telegram account
2. Lists ALL groups and channels you're a member of
3. Shows each channel's **ID**, **title**, and **type**
4. Allows manual search by channel name
5. Allows direct ID verification

**Example Output:**
```
========================================================================
📋 ALL FOUND CHANNELS AND GROUPS:
========================================================================

1. Mrbluemax Forex Academy
   Type:     Channel
   ID:       -1001234567890
   📋 Config: -1001234567890
   ------------------------------------------------------------------------

2. Trading Signals VIP
   Type:     Group/Supergroup
   ID:       -1009876543210
   📋 Config: -1009876543210
   ------------------------------------------------------------------------
```

**Copy the ID** (including the minus sign) and add it to `config.yaml`.

> **Alternative Methods:**
> - Forward a message from the channel to [@userinfobot](https://t.me/userinfobot)
> - Check the URL at [web.telegram.org](https://web.telegram.org) (add `-100` prefix for supergroups)

### Step 4: Get MT5 Credentials
1. Open MetaTrader 5
2. Go to **File → Login to Trade Account**
3. Note your:
   - **Login** (account number)
   - **Password** (trading password, NOT investor password)
   - **Server** (e.g., `ICMarkets-Demo01`)
4. Find MT5 path: Usually `C:/Program Files/MetaTrader 5/terminal64.exe`

### Step 5: Configure Environment Variables
Create a `.env` file in the `trading_bot` directory:

```env
# Telegram API (from my.telegram.org)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_PHONE=+1234567890

# MT5 Credentials
MT5_LOGIN=12345678
MT5_PASSWORD=your_trading_password
MT5_SERVER=YourBroker-Server
```

> **Security Warning**: Never commit `.env` to version control. Add it to `.gitignore`.

### Step 6: Configure Trading Settings
Edit `config.yaml` and add the channel IDs from `find_all_groups.py`:

```yaml
# Telegram channels to monitor (use IDs from find_all_groups.py)
# You can monitor multiple channels - add one per line
channels:
  - -1001234567890    # Mrbluemax Forex Academy (example)
  - -1009876543210    # Another signal channel (optional)

# Path to MT5 terminal
mt5_path: "C:/Program Files/MetaTrader 5/terminal64.exe"

# Trading settings
lot_size: 0.01          # Trade size (0.01 = micro lot)
max_slippage: 10        # Maximum slippage in points
magic_number: 234567    # Unique identifier for bot trades

# IMPORTANT: Start with false, set to true only when ready
trading_enabled: false
```

> **Tip**: Run `python find_all_groups.py` first, then copy-paste the channel IDs directly into `config.yaml`.

## Usage

### Running the Bot
```bash
cd trading_bot
python main.py
```

### First Run
On first run, Telegram will ask for verification:
1. Enter your phone number
2. Enter the verification code sent to Telegram
3. Session is saved to `bot_session.session`

### Expected Output
```
==================================================
Starting Telegram-to-MT5 Trading Bot
==================================================
Connecting to Telegram...
Connected as: YourName (+1234567890)

Verifying channel access...
✅ Channel -1001234567890: Signal Channel (ID: 1234567890)

Initializing MetaTrader 5...
✅ MT5 Account: 12345678 | Balance: 10000.00

==================================================
BOT STATUS
==================================================
   Channels monitored: [-1001234567890]
   MT5 status: READY
   Mode: DRY-RUN
   Lot size: 0.01
==================================================
Listening for signals...
```

### Modes

| Mode | `trading_enabled` | Behavior |
|------|-------------------|----------|
| **Dry-Run** | `false` | Detects and logs signals, no trades |
| **Live Trading** | `true` | Executes real trades on MT5 |

> **Recommendation**: Run in dry-run mode for at least 24 hours to verify signal detection before enabling live trading.

## Signal Processing Flow

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────┐
│ Telegram        │────▶│ SignalParser │────▶│ MT5Handler  │────▶│  MT5    │
│ Channel         │     │              │     │             │     │Terminal │
└─────────────────┘     └──────────────┘     └─────────────┘     └─────────┘
        │                      │                    │
        └──────────────────────┴────────────────────┘
                               │
                        ┌──────▼──────┐
                        │   SQLite    │
                        │  Database   │
                        └─────────────┘
```

## Database

Signals and messages are stored in `signals.db`:

### View Recent Signals
```bash
sqlite3 signals.db "SELECT * FROM signals ORDER BY timestamp DESC LIMIT 10;"
```

### View Statistics
```bash
sqlite3 signals.db "
SELECT
    COUNT(*) as total_signals,
    SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN status='ERROR' THEN 1 ELSE 0 END) as failed
FROM signals;"
```

## Troubleshooting

### Telegram Issues

| Error | Solution |
|-------|----------|
| `Channel NOT FOUND` | Verify you're a member of the channel |
| `FloodWaitError` | Bot is rate-limited, will auto-retry |
| `AuthKeyUnregistered` | Delete `bot_session.session` and restart |

### MT5 Issues

| Error | Solution |
|-------|----------|
| `MT5 init failed` | Check path, login, password, server |
| `Autotrading disabled` | Enable "Algo Trading" in MT5 toolbar |
| `Symbol not found` | Symbol may not be available on your broker |
| `No funds` | Check account balance/margin |
| `Market closed` | Trading hours restriction |

### Common Fixes
1. **MT5 not connecting**: Run MT5 terminal once manually before starting bot
2. **Signals not detected**: Check channel ID format (must include `-100` prefix)
3. **Trades not executing**: Verify `trading_enabled: true` in config.yaml

## Project Structure

```
trading_bot/
├── main.py              # Entry point, TradingBot class
├── parser.py            # Signal parsing logic
├── mt5_handler.py       # MT5 API wrapper
├── db_utils.py          # SQLite database operations
├── config.py            # Configuration loader
├── symbol_resolver.py   # Alias to symbol mapping
├── find_all_groups.py   # Utility: Find all Telegram channel IDs
├── config.yaml          # User settings
├── requirements.txt     # Python dependencies
├── .env                 # Secrets (create this)
├── signals.db           # Database (auto-created)
├── bot_session.session  # Telegram session (auto-created)
└── trading_bot.log      # Log file (auto-created)
```

## Security Considerations

- **Never share** your `.env` file or `bot_session.session`
- Use a **dedicated trading account** with limited funds for testing
- Start with **small lot sizes** (0.01) until confident
- Monitor the bot during market hours initially
- Set up **alerts** for critical errors in production

## License

MIT License - See LICENSE file for details.

## Disclaimer

This software is for educational purposes only. Trading forex and CFDs carries significant risk. Past performance is not indicative of future results. The authors are not responsible for any financial losses incurred through the use of this software.

---

**Built with Python, Telethon, and MetaTrader5**
