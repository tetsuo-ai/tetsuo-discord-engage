from .base_raid import BaseRaid
import discord
from discord.ext import commands
from datetime import datetime, timezone
import os
import asyncio
from playwright.async_api import async_playwright
import random
from .scrape_utils import ScrapeUtils
import logging
logger = logging.getLogger('tetsuo_bot.cmc_raid')

class CMCRaid(BaseRaid):
    def __init__(self, bot):
        super().__init__(bot)
        self.browser = None
        self.target_url = "https://coinmarketcap.com/dexscan/solana/2KB3i5uLKhUcjUwq3poxHpuGGqBWYwtTk5eG9E5WnLG6/"
        self.raid_channel_id = int(os.getenv('RAID_CHANNEL_ID', 0)) or None

    async def setup_playwright(self):
        """Initialize the Playwright browser"""
        if not self.browser:
            try:
                playwright = await async_playwright().start()
                self.browser = await playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                logger.info("Playwright browser initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing Playwright: {e}", exc_info=True)
                raise e

    async def get_metrics(self):
        """Get current upvote count from CMC"""
        if not self.browser:
            await self.setup_playwright()

        try:
            # Get randomized headers
            headers = ScrapeUtils.get_random_headers()
            context = await self.browser.new_context(
                user_agent=headers['User-Agent'],
                extra_http_headers={k:v for k,v in headers.items() if k != 'User-Agent'}
            )
            
            page = await context.new_page()
            await page.set_viewport_size({
                "width": random.randint(1024, 1920),
                "height": random.randint(768, 1080)
            })

            try:
                logger.info("Loading CMC metrics")
                await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
                
                # Random initial wait for page load
                await ScrapeUtils.random_delay(random.uniform(3, 7))
                
                # Simulate human-like mouse movements
                for _ in range(random.randint(2, 4)):
                    await page.mouse.move(
                        random.randint(0, 1000),
                        random.randint(0, 700)
                    )
                    await asyncio.sleep(random.uniform(0.1, 0.3))

                # Random scroll
                await page.evaluate(f'window.scrollTo(0, {random.randint(100, 300)})')
                await asyncio.sleep(random.uniform(0.5, 1.5))
                
                # Try to get the upvote count with a more human-like approach
                try:
                    element = await page.wait_for_selector('.thumb-row-up + span', timeout=5000)
                    if element:
                        # Move mouse near the element before reading
                        box = await element.bounding_box()
                        if box:
                            await page.mouse.move(
                                box['x'] + random.randint(5, 20),
                                box['y'] + random.randint(5, 10)
                            )
                            await asyncio.sleep(random.uniform(0.2, 0.5))
                            
                        thumb_text = await element.text_content()
                        logger.info(f"Found upvote count: {thumb_text}")
                        try:
                            return int(thumb_text.strip())
                        except ValueError:
                            logger.warning(f"Could not convert value to int: {thumb_text}")
                            return 0
                except Exception as e:
                    logger.error(f"Error getting upvote count: {e}", exc_info=True)
                    return 0

            except Exception as e:
                logger.error(f"Error during page load: {e}", exc_info=True)
                return 0
                
            finally:
                if 'page' in locals():
                    await page.close()
                if 'context' in locals():
                    await context.close()
                    
        except Exception as e:
            logger.error(f"Browser error: {e}", exc_info=True)
            return 0

    async def create_progress_embed(self, current_value, target_value):
        """Create progress embed for CMC raids"""
        embed = discord.Embed(
            title="🎯 CMC Engagement Challenge",
            description="Help support by upvoting!",
            color=0x00FF00
        )
        
        percentage = (current_value/target_value*100) if target_value > 0 else 0
        progress_bar = self.create_progress_bar(current_value, target_value)
        
        status_emoji = "✅" if percentage >= 100 else "🔸" if percentage >= 75 else "🔹"
        
        embed.add_field(
            name="👍 Upvotes Progress",
            value=(
                f"{status_emoji} Progress: {progress_bar} {percentage:.1f}%\n"
                f"Current: **{current_value}** / Target: **{target_value}**"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📝 Link",
            value=f"[Click to vote]({self.target_url})",
            inline=False
        )
        
        embed.timestamp = datetime.now(timezone.utc)
        embed.set_footer(text="Last updated")
        
        return embed

    async def monitor_raid(self, ctx, target_value, timeout_minutes=15):
        """Monitor the raid progress"""
        start_time = datetime.now(timezone.utc)
        
        # Initial lock message
        lock_embed = discord.Embed(
            title="🚨 CHANNEL LOCKED 🚨",
            description="🔒 This channel is locked until the upvote target is met! 🔒",
            color=0xFF0000
        )
        lock_embed.set_footer(text="Channel will automatically unlock when target is reached")
        lock_message = await ctx.send(embed=lock_embed)
        
        # Initial progress message
        current_value = await self.get_metrics()
        progress_embed = await self.create_progress_embed(current_value, target_value)
        progress_message = await ctx.send(embed=progress_embed)
        
        self.engagement_targets[ctx.channel.id] = {
            'target': target_value,
            'start_time': start_time,
            'message_id': progress_message.id,
            'lock_message_id': lock_message.id
        }
        
        while self.locked_channels.get(ctx.channel.id):
            try:
                # Check timeout
                if (datetime.now(timezone.utc) - start_time).total_seconds() > timeout_minutes * 60:
                    await self.unlock_channel(ctx.channel)
                    await lock_message.delete()
                    
                    timeout_embed = await self.create_progress_embed(current_value, target_value)
                    timeout_embed.color = 0xFF6B6B
                    timeout_embed.add_field(
                        name="⏰ RAID TIMED OUT! ⏰",
                        value=f"```diff\n- Raid ended after {timeout_minutes} minutes! Channel unlocked! 🔓\n```",
                        inline=False
                    )
                    await progress_message.edit(embed=timeout_embed)
                    return

                # Get current metrics
                current_value = await self.get_metrics()
                
                # Check if target met
                if current_value >= target_value:
                    await self.unlock_channel(ctx.channel)
                    await lock_message.delete()
                    
                    final_embed = await self.create_progress_embed(current_value, target_value)
                    final_embed.add_field(
                        name="🎉 CHALLENGE COMPLETE! 🎉",
                        value="```diff\n+ Target reached! Channel unlocked! 🔓\n```",
                        inline=False
                    )
                    await progress_message.edit(embed=final_embed)
                    return
                    
                # Update progress
                progress_embed = await self.create_progress_embed(current_value, target_value)
                await progress_message.edit(embed=progress_embed)
                
            except Exception as e:
                logger.error(f"Error monitoring raid: {e}", exc_info=True)
            
            # Replace fixed sleep with random delay
            await ScrapeUtils.random_delay(30)

    @commands.command(name='raid_cmc')
    @commands.has_permissions(manage_channels=True)
    async def raid_cmc(self, ctx, *, targets):
        """Start a CMC upvote raid
        
        Usage: !raid_cmc likes:<target> [timeout:<minutes>]
        Example: !raid_cmc likes:425 timeout:30"""
        
        if not await self.check_raid_channel(ctx):
            return
            
        if ctx.channel.id in self.locked_channels:
            await ctx.send("There's already an active raid in this channel!")
            return
            
        try:
            # Parse targets
            target_value = None
            timeout_minutes = 15  # Default timeout
            
            for pair in targets.split():
                try:
                    if ':' not in pair:
                        continue
                        
                    metric, value = pair.split(':', 1)
                    metric = metric.lower()
                    
                    try:
                        value = int(value)
                        if metric == 'timeout':
                            timeout_minutes = max(1, min(120, value))
                        elif metric == 'likes' and value > 0 and value <= 1000000:
                            target_value = value
                    except ValueError:
                        continue
                        
                except Exception:
                    continue

            if target_value is None:
                await ctx.send("Please provide a valid target (e.g., `likes:425`)")
                return
            
            # Lock channel
            await self.lock_channel(ctx.channel)
            
            # Start monitoring
            await self.monitor_raid(ctx, target_value, timeout_minutes)
            
        except Exception as e:
            logger.error(f"Error in raid_cmc: {e}", exc_info=True)
            await ctx.send(f"Error: {str(e)}")
            await self.unlock_channel(ctx.channel)

    def cog_unload(self):
        if self.browser:
            asyncio.create_task(self.browser.close())

async def setup(bot):
    await bot.add_cog(CMCRaid(bot))