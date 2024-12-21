import discord
from discord.ext import commands
import asyncio
import aiohttp
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

class WhaleMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.pool_address = "2KB3i5uLKhUcjUwq3poxHpuGGqBWYwtTk5eG9E5WnLG6"
        self.min_usd_threshold = 1000
        self.monitor_task = None
        self.cleanup_task = None
        self.alert_channel_id = int(os.getenv('WHALE_ALERT_CHANNEL', 0))
        self.headers = {
            'accept': 'application/json;version=20230302',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.api_url = f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{self.pool_address}/trades"
        self.seen_transactions = {}
        self.bot_start_time = None

    async def cleanup_messages(self):
        """Keep only the most recent 200 messages in the whale alert channel"""
        while True:
            try:
                # Explicitly check if we have a designated channel
                if not self.alert_channel_id:
                    await asyncio.sleep(60)
                    continue
                    
                channel = self.bot.get_channel(self.alert_channel_id)
                if not channel:
                    await asyncio.sleep(60)
                    continue

                # Double-check we're in the right channel before doing any cleanup
                if not isinstance(channel, discord.TextChannel):
                    print("Whale alert channel is not a text channel")
                    await asyncio.sleep(60)
                    continue

                # Get messages only from the designated channel
                messages = []
                async for message in channel.history(limit=None):
                    if message.channel.id != self.alert_channel_id:
                        continue
                        
                    # Skip pinned messages
                    if message.pinned:
                        continue
                    messages.append(message)
                
                # If we have more than 200 messages, delete the oldest ones
                if len(messages) > 200:
                    # Sort by timestamp, newest first
                    messages.sort(key=lambda x: x.created_at, reverse=True)
                    
                    # Delete messages after the first 200
                    deleted_count = 0
                    for message in messages[200:]:
                        try:
                            # One final channel check before deletion
                            if message.channel.id == self.alert_channel_id:
                                await message.delete()
                                deleted_count += 1
                                # Small delay to avoid rate limits
                                await asyncio.sleep(1)
                        except Exception as e:
                            print(f"Error deleting message in whale channel: {e}")
                            continue
                    
                    if deleted_count > 0:
                        print(f"Cleaned up {deleted_count} messages from whale alert channel")
                
                # Run cleanup every 5 minutes
                await asyncio.sleep(300)
                    
            except Exception as e:
                print(f"Error in whale channel cleanup: {e}")
                await asyncio.sleep(60)

    async def start_monitoring(self):
        """Monitor trades with proper rate limiting"""
        if not self.session:
            self.session = aiohttp.ClientSession(headers=self.headers)

        # Set the bot start time on first run with UTC timezone
        if self.bot_start_time is None:
            self.bot_start_time = datetime.now(timezone.utc)
            print(f"Whale Monitor: Initialized at {self.bot_start_time}")

        # Track our API calls
        request_times = []
        
        while True:
            try:
                if not self.alert_channel_id:
                    await asyncio.sleep(30)
                    continue

                # Clean up old request timestamps
                current_time = datetime.now(timezone.utc)
                request_times = [t for t in request_times 
                            if (current_time - t).total_seconds() < 60]

                # Check if we're about to exceed rate limit
                if len(request_times) >= 30:
                    # Wait until oldest request is more than 60s old
                    wait_time = 60 - (current_time - request_times[0]).total_seconds()
                    if wait_time > 0:
                        print(f"Rate limit approaching, waiting {wait_time:.1f}s")
                        await asyncio.sleep(wait_time)
                    continue

                params = {
                    'trade_volume_in_usd_greater_than': self.min_usd_threshold
                }

                request_times.append(current_time)

                async with self.session.get(self.api_url, params=params) as response:
                    if response.status == 429:  # Rate limit
                        retry_after = int(response.headers.get('Retry-After', 30))
                        print(f"Rate limited, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                        
                    if response.status != 200:
                        print(f"API error: {response.status}")
                        await asyncio.sleep(30)
                        continue

                    data = await response.json()
                    await self.process_trades(data)

                # Fixed 2-second interval between requests
                await asyncio.sleep(2)

            except aiohttp.ClientError as e:
                print(f"Connection error: {e}")
                await asyncio.sleep(30)
            except Exception as e:
                print(f"Monitoring error: {e}")
                await asyncio.sleep(30)

    async def process_trades(self, data):
        """Process new trades from the API"""
        if 'data' not in data or not data['data']:
            return

        current_time = datetime.now(timezone.utc)

        for trade in data['data']:
            try:
                attrs = trade['attributes']
                tx_hash = attrs['tx_hash']
                
                # Parse the trade timestamp with proper timezone handling
                trade_time = datetime.fromisoformat(attrs['block_timestamp'].replace('Z', '+00:00'))
                
                # Skip if trade happened before bot start
                if trade_time < self.bot_start_time:
                    continue

                # Skip if we've already seen this transaction
                if tx_hash in self.seen_transactions:
                    continue

                # Skip non-buys
                if attrs['kind'] != 'buy':
                    continue

                # Verify the trade meets our minimum threshold
                usd_value = float(attrs['volume_in_usd'])
                if usd_value < self.min_usd_threshold:
                    continue

                # Add to seen transactions
                self.seen_transactions[tx_hash] = current_time

                await self.send_whale_alert(
                    transaction=tx_hash,
                    usd_value=usd_value,
                    price_usd=float(attrs['price_to_in_usd']),
                    amount_tokens=float(attrs['to_token_amount']),
                    price_impact=0,
                    trade_time=trade_time  # Add timestamp to the call
                )

            except Exception as e:
                print(f"Error processing trade: {e}")
                continue

        # Clean up old transactions (older than 1 hour)
        self.seen_transactions = {
            hash: time 
            for hash, time in self.seen_transactions.items()
            if (current_time - time).total_seconds() < 3600
        }
    
    async def send_whale_alert(self, transaction, usd_value, price_usd, amount_tokens, price_impact, trade_time):
        """Send whale alert to Discord"""
        if not self.alert_channel_id:
            print("No alert channel configured")
            return
                
        channel = self.bot.get_channel(self.alert_channel_id)
        if not channel:
            print(f"Could not find channel with ID: {self.alert_channel_id}")
            return

        print(f"Sending whale alert for ${usd_value:,.2f}")

       # Get appropriate GIF based on size (Using image/gif links as placeholders)
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

        # Remove emoji wall entirely since we'll use GIF
        embed = discord.Embed(
            title=title,
            description=excitement,
            color=0x00ff00,
            timestamp=trade_time
        )
        
        embed.set_image(url=gif_url)  # For full-width GIF

        # Keep all values on one line
        info_line = f"💰 ${usd_value:,.2f} • 🎯 ${price_usd:.6f} • 📊 {amount_tokens:,.0f} TETSUO"
        embed.add_field(
            name="Transaction Details",
            value=info_line,
            inline=False
        )

        embed.add_field(
            name="🔍 Transaction",
            value=f"[View on Solscan](https://solscan.io/tx/{transaction})",
            inline=False
        )

        try:
            await channel.send(embed=embed)
            print(f"Successfully sent alert for tx: {transaction}")
        except Exception as e:
            print(f"Error sending whale alert: {e}")

    @commands.command(name='set_whale_channel')
    @commands.has_permissions(administrator=True)
    async def set_whale_channel(self, ctx, channel_id: str):
        """Set the whale alert channel by ID"""
        try:
            self.alert_channel_id = int(channel_id)
            
            # Update environment
            env_path = '.env'
            existing_lines = []
            updated = False
            
            if os.path.exists(env_path):
                with open(env_path, 'r') as file:
                    existing_lines = file.readlines()
                    
                for i, line in enumerate(existing_lines):
                    if line.strip().startswith('WHALE_ALERT_CHANNEL='):
                        existing_lines[i] = f'WHALE_ALERT_CHANNEL={channel_id}\n'
                        updated = True
                        break
                
                if not updated:
                    existing_lines.append(f'WHALE_ALERT_CHANNEL={channel_id}\n')
            else:
                existing_lines = [f'WHALE_ALERT_CHANNEL={channel_id}\n']
            
            with open(env_path, 'w') as file:
                file.writelines(existing_lines)
            
            os.environ['WHALE_ALERT_CHANNEL'] = channel_id
            
            await ctx.send(f"✅ Channel ID {channel_id} has been set for whale alerts.\nMonitoring buys above ${self.min_usd_threshold:,}", delete_after=30)
            
        except ValueError:
            await ctx.send("❌ Please provide a valid channel ID", delete_after=10)
        except Exception as e:
            print(f"Error setting whale channel: {e}")
            await ctx.send(f"❌ Error setting whale channel: {str(e)}", delete_after=30)

    @commands.command(name='set_whale_minimum')
    @commands.has_permissions(administrator=True)
    async def set_whale_minimum(self, ctx, amount: int):
        """Set minimum USD value for whale alerts
        
        Usage: !set_whale_minimum <amount>
        Example: !set_whale_minimum 15000"""
        
        if amount < 1000:  # Prevent silly low values
            await ctx.send("❌ Minimum value must be at least $1,000", delete_after=10)
            return
            
        if amount > 1000000:  # Prevent absurdly high values
            await ctx.send("❌ Minimum value cannot exceed $1,000,000", delete_after=10)
            return
            
        self.min_usd_threshold = amount
        await ctx.send(
            f"✅ Whale alert minimum set to ${amount:,}\n"
            f"Now monitoring TETSUO buys above this value.",
            delete_after=30
        )

    @commands.command(name='whale_channel')
    @commands.has_permissions(manage_channels=True)
    async def whale_channel(self, ctx):
        """Display information about the current whale alert channel"""
        if not self.alert_channel_id:
            await ctx.send("❌ No whale alert channel has been set! An administrator must use !set_whale_channel to configure one.", delete_after=30)
            return
            
        channel = self.bot.get_channel(self.alert_channel_id)
        if not channel:
            await ctx.send("⚠️ Configured whale alert channel not found! The channel may have been deleted.", delete_after=30)
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
            value=f"${self.min_usd_threshold:,}",
            inline=False
        )
        
        if ctx.channel.id == self.alert_channel_id:
            embed.add_field(
                name="Status",
                value="✅ You are in the whale alert channel",
                inline=False
            )
        else:
            embed.add_field(
                name="Status",
                value=f"ℹ️ Whale alerts go to <#{self.alert_channel_id}>",
                inline=False
            )
            
        await ctx.send(embed=embed, delete_after=30)

    @commands.Cog.listener()
    async def on_ready(self):
        """Start monitoring when bot is ready"""
        if not self.monitor_task:
            self.monitor_task = self.bot.loop.create_task(self.start_monitoring())
            print("Whale Monitor: Started monitoring buys")
        if not self.cleanup_task:
            self.cleanup_task = self.bot.loop.create_task(self.cleanup_messages())
            print("Whale Monitor: Started channel cleanup task")

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self.monitor_task:
            self.monitor_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())

async def setup(bot):
    await bot.add_cog(WhaleMonitor(bot))