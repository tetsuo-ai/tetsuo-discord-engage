# 🐳 Tetsuo Discord Engage

A Discord bot for crypto community engagement tracking and coordination. Monitor whale activity, track sentiment across platforms, and coordinate community engagement raids.

## ✨ Features

### 🎯 Raid Coordination
- Twitter/X engagement tracking
- CMC upvote monitoring
- GeckoTerminal sentiment tracking
- GMGN.ai sentiment tracking
- Dextools sentiment tracking
- Automated channel management
- Progress tracking and notifications

### 🐋 Whale Watching
- Real-time transaction monitoring
- Customizable alert thresholds
- Automated alerts with transaction details
- GIF reactions based on transaction size

### 📊 Metrics Dashboard
- Live sentiment tracking across platforms
- Trend indicators
- Automatic updates every 5 minutes
- Pinned message management

## 🛠️ Setup

### Prerequisites
- Python 3.11 (Required - newer versions not supported)
- Discord Bot Token
- Linux/Mac/Windows

### Quick Install
```bash
# Clone the repository
git clone https://github.com/tetsuo-ai/tetsuo-discord-engage
cd tetsuo-discord-engage

# Create and activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright dependencies
playwright install --with-deps --only-shell
```

### Configuration
Create a `.env` file in the root directory:
```env
DISCORD_TOKEN=your_discord_bot_token
RAID_CHANNEL_ID=your_raid_channel_id  # Optional
WHALE_ALERT_CHANNEL=your_whale_channel_id  # Optional
```

### Running the Bot
```bash
# Start the bot
python main.py
```

## 🎮 Commands

### Raid Management
- `!raid <tweet_url> <targets>` - Start a Twitter raid
  ```
  Example: !raid https://twitter.com/user/123 likes:100 retweets:50 replies:25 timeout:30
  ```
- `!raid_cmc likes:<target> [timeout:<minutes>]` - Start a CMC raid
- `!raid_gecko sentiment:<target> [timeout:<minutes>]` - Start a Gecko raid
- `!raid_gmgn sentiment:<target> [timeout:<minutes>]` - Start a GMGN raid
- `!raid_dextools sentiment:<target> [timeout:<minutes>]` - Start a Dextools raid
- `!raid_stop` - End current raid and unlock channel

### Channel Configuration
- `!set_raid_channel <channel_id>` - Set raid coordination channel
- `!raid_channel` - Show current raid channel info
- `!set_whale_channel <channel_id>` - Set whale alert channel
- `!whale_channel` - Show whale alert configuration
- `!set_whale_minimum <amount>` - Set minimum USD value for whale alerts

## 🔧 Maintenance

### Channel Management
The bot automatically:
- Cleans up old messages in raid channels
- Maintains pinned metrics dashboard
- Removes outdated alerts
- Updates sentiment metrics every 5 minutes

### Raid History
- Tracks raid performance
- Maintains success/timeout statistics
- Auto-cleans history older than 24 hours

## ⚠️ Common Issues

1. **Python Version Conflicts**
   - Must use Python 3.11
   - Newer versions cause discord.py compatibility issues

2. **Playwright Installation**
   - If you encounter Playwright issues, run:
   ```bash
   playwright install --with-deps
   ```

3. **Channel Permission Errors**
   - Bot needs Manage Messages permissions
   - Must be able to Pin Messages
   - Requires Send Messages permissions

## 📚 Additional Notes

- Bot requires specific intents (Members, Message Content, Presence)
- Recommended to run in a dedicated server channel
- Whale alerts use configurable thresholds
- All timeouts can be customized per raid

## 🤝 Support
Created and maintained by the Tetsuo AI team.

## 📄 License
MIT - See [LICENSE](LICENSE) for details.