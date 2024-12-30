import discord
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import websockets
from typing import Optional, Dict, Any
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
    API_URL: str = "http://localhost:8080"
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
        """Keep only the most recent 200 messages in the whale alert channel"""
        while True:
            try:
                if not self.config.channel_id:
                    await asyncio.sleep(60)
                    continue
                    
                channel = self.bot.get_channel(self.config.channel_id)
                if not channel:
                    await asyncio.sleep(60)
                    continue

                if not isinstance(channel, discord.TextChannel):
                    logger.warning("Whale alert channel is not a text channel")
                    await asyncio.sleep(60)
                    continue

                messages = []
                async for message in channel.history(limit=None):
                    if message.channel.id != self.config.channel_id:
                        continue
                        
                    if message.pinned:
                        continue
                    messages.append(message)
                
                if len(messages) > 200:
                    messages.sort(key=lambda x: x.created_at, reverse=True)
                    
                    deleted_count = 0
                    for message in messages[200:]:
                        try:
                            if message.channel.id == self.config.channel_id:
                                await message.delete()
                                deleted_count += 1
                                await asyncio.sleep(1)
                        except Exception as e:
                            logger.error(f"Error deleting message: {e}", exc_info=True)
                            continue
                    
                    if deleted_count > 0:
                        logger.info(f"Cleaned up {deleted_count} messages from whale alert channel")
                
                await asyncio.sleep(300)
                    
            except Exception as e:
                logger.error(f"Error in whale channel cleanup: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def start_monitoring(self):
        """Monitor whale alerts via WebSocket"""
        while True:
            try:
                async with websockets.connect(self.settings.WS_URL) as ws:
                    logger.info("WebSocket connected to whale alert service")
                    
                    while True:
                        try:
                            message = await ws.recv()
                            data = json.loads(message)
                            
                            if data.get('event_type') == 'new_whale':
                                logger.info("New whale event received!")
                                await self.handle_whale_alert(data['data'])
                                
                        except websockets.ConnectionClosed:
                            logger.warning("WebSocket connection closed")
                            break
                        except json.JSONDecodeError as je:
                            logger.error(f"JSON decode error: {je}")
                        except Exception as e:
                            logger.error(f"WebSocket message processing error: {e}")
                            
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                
            if not self.bot.is_closed():
                await asyncio.sleep(5)
            else:
                break

    async def handle_whale_alert(self, data: Dict[str, Any]):
        """Process and send whale alert to Discord"""
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

        alert = data['alert']
        token_stats = data.get('token_stats', {})

        # Determine alert type based on size
        usd_value = transaction['amount_usd']
        if usd_value >= 50000:
            title = "🐋 ABSOLUTELY MASSIVE WHALE ALERT! 🐋"
            excitement = "HOLY MOTHER OF ALL WHALES!"
            gif_url = "https://media1.tenor.com/m/6TbYHcZ2wQwAAAAd/whale-ocean.gif"
        elif usd_value >= 20000:
            title = "🌊 HUGE Whale Alert! 🌊"
            excitement = "Now that's what I call a splash!"
            gif_url = "https://media1.tenor.com/m/6TbYHcZ2wQwAAAAd/whale-ocean.gif"
        elif usd_value >= 5000:
            title = "💦 Big Whale Alert! 💦"
            excitement = "Making waves!"
            gif_url = "https://media1.tenor.com/m/6TbYHcZ2wQwAAAAd/whale-ocean.gif"
        elif usd_value >= 2000:
            title = "💫 Shark Alert! So Ferocious! 💫"
            excitement = "Nice buy!"
            gif_url = "https://media1.tenor.com/m/9jbUEncewVkAAAAd/ebisu-mappa.gif"
        else:
            title = "✨ Baby Shark Alert ✨"
            excitement = "Every shark starts somewhere!"
            gif_url = "https://media1.tenor.com/m/x-rwdPINKUYAAAAd/tuna-guitar.gif"

        embed = discord.Embed(
            title=title,
            description=excitement,
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_image(url=gif_url)

        info_line = (
            f"💰 ${transaction['amount_usd']:,.2f} • "
            f"🎯 ${transaction['price_usd']:.6f} • "
            f"📊 {transaction['amount_tokens']:,.0f} TETSUO"
        )
        embed.add_field(
            name="Transaction Details",
            value=info_line,
            inline=False
        )

        if token_stats:
            market_stats = (
                f"📈 24h Volume: ${float(token_stats.get('volume_24h', 0)):,.2f}\n"
                f"💎 Market Cap: ${float(token_stats.get('market_cap', 0)):,.2f}\n"
                f"💵 Current Price: ${float(token_stats.get('price_usd', 0)):,.8f}"
            )
            embed.add_field(
                name="Market Stats",
                value=market_stats,
                inline=False
            )

        embed.add_field(
            name="🔍 Transaction",
            value=f"[View on Solscan](https://solscan.io/tx/{transaction['transaction_hash']})",
            inline=False
        )

        try:
            await channel.send(embed=embed)
            logger.info(f"Successfully sent alert for tx: {transaction['transaction_hash']}")
        except Exception as e:
            logger.error(f"Error sending whale alert: {e}", exc_info=True)

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

async def setup(bot):
    await bot.add_cog(WhaleMonitor(bot))