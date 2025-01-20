import discord
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import websockets
from typing import Optional
import logging
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from functools import lru_cache

logger = logging.getLogger('tetsuo_bot.whale_watcher')

class BotConfig(BaseModel):
    channel_id: Optional[int] = None
    min_threshold: int = 5000
    notifications_enabled: bool = True

    @classmethod
    def load(cls) -> 'BotConfig':
        config_path = Path("discord_whale_config.json")
        if config_path.exists():
            return cls.parse_raw(config_path.read_text())
        return cls()

    def save(self):
        config_path = Path("discord_whale_config.json")
        config_path.write_text(self.model_dump_json(indent=2))

class Settings(BaseSettings):
    """Discord bot whale watcher settings"""
    WS_URL: str = "ws://localhost:8080/ws"
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = 'allow'

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

class WhaleMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = BotConfig.load()
        self.settings = get_settings()
        self._ws_task = None
        self.cleanup_task = None

    async def cleanup_messages(self):
        """Delete whale alert messages older than 3 days"""
        while True:
            try:
                if not self.config.channel_id:
                    await asyncio.sleep(30)
                    continue
                    
                channel = self.bot.get_channel(self.config.channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    await asyncio.sleep(30)
                    continue

                cutoff = datetime.now(timezone.utc).timestamp() - (3 * 24 * 60 * 60)  # 3 days in seconds
                deleted = 0
                
                async for message in channel.history(limit=None):
                    if (not message.pinned and 
                        message.created_at.timestamp() < cutoff and 
                        message.author == self.bot.user):
                        try:
                            await message.delete()
                            deleted += 1
                            await asyncio.sleep(1)  # Rate limiting protection
                        except Exception as e:
                            logger.error(f"Error deleting message: {e}")

                if deleted:
                    logger.info(f"Cleaned up {deleted} old whale alerts")
                
                await asyncio.sleep(300)  # Check every 5 minutes
                    
            except Exception as e:
                logger.error(f"Whale cleanup error: {e}")
                await asyncio.sleep(30)

    async def handle_whale_alert(self, data: dict):
        """Process and send whale alert to Discord"""
        logger.info(f"Handling whale alert. Config: {self.config}")
        
        if not self.config.channel_id:
            logger.warning("No channel ID configured")
            return
            
        if not self.config.notifications_enabled:
            logger.info("Notifications are disabled")
            return
            
        channel = self.bot.get_channel(self.config.channel_id)
        if not channel:
            logger.error(f"Could not find channel with ID: {self.config.channel_id}")
            return

        transaction = data['transaction']
        if transaction['amount_usd'] < self.config.min_threshold:
            logger.info(f"Transaction below threshold: ${transaction['amount_usd']} < ${self.config.min_threshold}")
            return

        alert_data = data['alert']
        token_stats = data['token_stats']
        
        # Create embed from alert data
        embed = discord.Embed(
            title=alert_data['title'],
            description=(
                f"💰 Buy Size: ${transaction['amount_usd']:,.2f}\n"
                f"🎯 Buy Price: ${transaction['price_usd']:.8f}\n"
                f"📊 Amount: {transaction['amount_tokens']:,.2f} TETSUO\n"
                f"📈 24h Volume: ${float(token_stats['volume_24h'] or 0):,.2f}\n"
                f"💎 Market Cap: ${float(token_stats['market_cap'] or 0):,.2f}\n"
                f"💵 Current Price: ${float(token_stats['price_usd'] or 0):.8f}\n"
                f"🔍 [View on Solscan](https://solscan.io/tx/{transaction['transaction_hash']})"
            ),
            color=alert_data['color'],
            timestamp=datetime.fromisoformat(alert_data['timestamp'])
        )

        if 'image' in alert_data and 'url' in alert_data['image']:
            embed.set_image(url=alert_data['image']['url'])

        try:
            await channel.send(embed=embed)
            logger.info(f"Successfully sent alert for tx: {transaction['transaction_hash']}")
        except Exception as e:
            logger.error(f"Error sending alert: {e}", exc_info=True)
            try:
                channel = await self.bot.fetch_channel(self.config.channel_id)
                logger.info(f"Channel details: {channel}")
            except Exception as channel_error:
                logger.error(f"Could not retrieve channel details: {channel_error}")

    async def start_monitoring(self):
        """Monitor whale alerts via WebSocket"""
        while True:
            try:
                async with websockets.connect(self.settings.WS_URL) as ws:
                    logger.info("WebSocket connected")
                    
                    while True:
                        try:
                            message = await ws.recv()
                            logger.info(f"Raw WebSocket message: {message}")
                            
                            data = json.loads(message)
                            logger.info(f"Parsed WebSocket data: {data}")
                            
                            if data.get('event_type') == 'new_whale':
                                logger.info("New whale event received!")
                                await self.handle_whale_alert(data['data'])
                            else:
                                logger.info(f"Received non-whale event: {data.get('event_type')}")
                                
                        except websockets.ConnectionClosed:
                            logger.warning("WebSocket connection closed")
                            break
                        except json.JSONDecodeError as je:
                            logger.error(f"JSON decode error: {je}")
                        except Exception as e:
                            logger.error(f"WebSocket message processing error: {e}")
                            
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                
            # Retry connection if disconnected
            if not self.bot.is_closed():
                await asyncio.sleep(5)
            else:
                break

    @commands.Cog.listener()
    async def on_ready(self):
        """Start monitoring when bot is ready"""
        if not self._ws_task:
            self._ws_task = self.bot.loop.create_task(self.start_monitoring())
            logger.info("Whale Monitor: Started monitoring")
        if not self.cleanup_task:
            self.cleanup_task = self.bot.loop.create_task(self.cleanup_messages())
            logger.info("Whale Monitor: Started channel cleanup task")

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self._ws_task:
            self._ws_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()

    @commands.command(name='set_whale_channel')
    @commands.has_permissions(administrator=True)
    async def set_whale_channel(self, ctx, channel_id: str):
        """Set the whale alert channel by ID"""
        try:
            channel_id = int(channel_id)
            channel = self.bot.get_channel(channel_id)
            
            if not channel:
                await ctx.send("❌ Could not find channel with that ID", delete_after=10)
                return
                
            if not isinstance(channel, discord.TextChannel):
                await ctx.send("❌ That is not a text channel", delete_after=10)
                return
            
            self.config.channel_id = channel_id
            self.config.save()
            
            await ctx.send(
                f"✅ Channel ID {channel_id} has been set for whale alerts.\n"
                f"Monitoring buys above ${self.config.min_threshold:,}", 
                delete_after=30
            )
            
        except ValueError:
            await ctx.send("❌ Please provide a valid channel ID", delete_after=10)
        except Exception as e:
            logger.error(f"Error setting whale channel: {e}", exc_info=True)
            await ctx.send(f"❌ Error setting whale channel: {str(e)}", delete_after=30)

    @commands.command(name='set_whale_minimum')
    @commands.has_permissions(administrator=True)
    async def set_whale_minimum(self, ctx, amount: int):
        """Set minimum USD value for whale alerts
        
        Usage: !set_whale_minimum <amount>
        Example: !set_whale_minimum 15000"""
        
        if amount < 1000:
            await ctx.send("❌ Minimum value must be at least $1,000", delete_after=10)
            return
            
        if amount > 1000000:
            await ctx.send("❌ Minimum value cannot exceed $1,000,000", delete_after=10)
            return
            
        self.config.min_threshold = amount
        self.config.save()
        
        await ctx.send(
            f"✅ Whale alert minimum set to ${amount:,}\n"
            f"Now monitoring TETSUO buys above this value.",
            delete_after=30
        )

    @commands.command(name='whale_channel')
    @commands.has_permissions(manage_channels=True)
    async def whale_channel(self, ctx):
        """Display information about the current whale alert channel"""
        if not self.config.channel_id:
            await ctx.send(
                "❌ No whale alert channel has been set! "
                "An administrator must use !set_whale_channel to configure one.", 
                delete_after=30
            )
            return
            
        channel = self.bot.get_channel(self.config.channel_id)
        if not channel:
            await ctx.send(
                "⚠️ Configured whale alert channel not found! "
                "The channel may have been deleted.", 
                delete_after=30
            )
            return
            
        embed = discord.Embed(
            title="🐋 Whale Alert Configuration",
            color=0x00FF00
        )
        
        embed.add_field(
            name="Alert Channel",
            value=f"#{channel.name} (`{channel.id}`)",
            inline=False
        )
        
        embed.add_field(
            name="Minimum Buy Size",
            value=f"${self.config.min_threshold:,}",
            inline=False
        )
        
        embed.add_field(
            name="Status",
            value="✅ Alerts are enabled" if self.config.notifications_enabled else "⛔ Alerts are disabled",
            inline=False
        )
        
        if ctx.channel.id == self.config.channel_id:
            embed.add_field(
                name="Current Channel",
                value="✅ You are in the whale alert channel",
                inline=False
            )
        else:
            embed.add_field(
                name="Current Channel",
                value=f"ℹ️ Whale alerts go to <#{self.config.channel_id}>",
                inline=False
            )
            
        await ctx.send(embed=embed, delete_after=30)

async def setup(bot):
    await bot.add_cog(WhaleMonitor(bot))