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
        self.alert_channel_id = int(os.getenv('WHALE_ALERT_CHANNEL', 0))
        self.headers = {
            'accept': 'application/json;version=20230302',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.api_url = f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{self.pool_address}/trades"
        self.seen_transactions = {}
        self.bot_start_time = None

    async def start_monitoring(self):
        """Monitor trades with proper rate limiting"""
        if not self.session:
            self.session = aiohttp.ClientSession(headers=self.headers)

        # Set the bot start time on first run with UTC timezone
        if self.bot_start_time is None:
            self.bot_start_time = datetime.now(timezone.utc)
            print(f"Whale Monitor: Initialized at {self.bot_start_time}")

        while True:
            try:
                if not self.alert_channel_id:
                    await asyncio.sleep(30)
                    continue

                params = {
                    'trade_volume_in_usd_greater_than': self.min_usd_threshold
                }

                print("Checking for new trades...")

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
                    print(f"Received {len(data.get('data', []))} trades")
                    await self.process_trades(data)

                    # Get and log cache control info
                    cache_control = response.headers.get('cache-control', '')
                    print(f"Cache-Control header: {cache_control}")
                    
                    if 'max-age=' in cache_control:
                        max_age = int(cache_control.split('max-age=')[1].split(',')[0])
                        print(f"Waiting {max_age} seconds based on cache control")
                        await asyncio.sleep(max_age)
                    else:
                        print("No cache control, using 15s default interval")
                        await asyncio.sleep(15)

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
                    price_impact=0
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

    async def send_whale_alert(self, transaction, usd_value, price_usd, amount_tokens, price_impact):
        """Send whale alert to Discord"""
        if not self.alert_channel_id:
            print("No alert channel configured")
            return
                
        channel = self.bot.get_channel(self.alert_channel_id)
        if not channel:
            print(f"Could not find channel with ID: {self.alert_channel_id}")
            return

        print(f"Sending whale alert for ${usd_value:,.2f}")

        # Calculate number of emojis (1 per $20)
        emoji_count = int(usd_value / 20)
        
        # Create excitement level based on size
        if usd_value >= 50000:
            title = "<:tetsuorage:1318799120105865317> ABSOLUTELY MASSIVE WHALE ALERT! <:tetsuorage:1318799120105865317>"
            excitement = "HOLY MOTHER OF ALL WHALES!"
        elif usd_value >= 20000:
            title = "<:tetsuoblueeyes:1318799118407307276> HUGE Whale Alert! <:tetsuoblueeyes:1318799118407307276>"
            excitement = "Now that's what I call a splash!"
        elif usd_value >= 5000:
            title = "<:ascii_dark:1318795848762523739> Big Whale Alert! <:ascii_dark:1318795848762523739>"
            excitement = "Making waves!"
        elif usd_value >= 2000:
            title = "<:ascii:1318795865267372042> Whale Alert! <:ascii:1318795865267372042>"
            excitement = "Nice buy!"
        else:
            title = "<:ascii:1318795865267372042> Baby Whale Alert <:ascii:1318795865267372042>"
            excitement = "Every whale starts somewhere!"

        # Create our emoji tsunami (cycle through all custom emojis)
        emojis = [
            '<:ascii:1318795865267372042>', 
            '<:ascii_dark:1318795848762523739>', 
            '<:tetsuorage:1318799120105865317>', 
            '<:tetsuoblueeyes:1318799118407307276>'
        ]
        emoji_wall = ''.join(emojis[i % len(emojis)] for i in range(emoji_count))

        embed = discord.Embed(
            title=title,
            description=f"{excitement}\n\n{emoji_wall}",
            color=0x00ff00
        )

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
    async def set_whale_channel(self, ctx):
        """Set the current channel as the whale alert channel"""
        self.alert_channel_id = ctx.channel.id
        
        env_path = '.env'
        new_var = f'WHALE_ALERT_CHANNEL={ctx.channel.id}'
        
        if os.path.exists(env_path):
            with open(env_path, 'r') as file:
                lines = file.readlines()
            
            found = False
            for i, line in enumerate(lines):
                if line.startswith('WHALE_ALERT_CHANNEL='):
                    lines[i] = f'{new_var}\n'
                    found = True
                    break
            
            if not found:
                lines.append(f'\n{new_var}\n')
            
            with open(env_path, 'w') as file:
                file.writelines(lines)
        else:
            with open(env_path, 'a') as file:
                file.write(f'{new_var}\n')
        
        await ctx.send(
            f"✅ This channel has been set for whale alerts.\n"
            f"Channel ID: `{ctx.channel.id}`\n"
            f"Monitoring buys above ${self.min_usd_threshold:,}", 
            delete_after=30
        )

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

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self.monitor_task:
            self.monitor_task.cancel()
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())

async def setup(bot):
    await bot.add_cog(WhaleMonitor(bot))