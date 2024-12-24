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
logger = logging.getLogger('tetsuo_bot.dextools_raid')

class DextoolsRaid(BaseRaid):
    def __init__(self, bot):
        super().__init__(bot)
        self.browser = None
        self.target_url = "https://www.dextools.io/app/en/solana/pair-explorer/2KB3i5uLKhUcjUwq3poxHpuGGqBWYwtTk5eG9E5WnLG6?t=1734332435607"
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
            except Exception as e:
                logger.error(f"Error initializing Playwright: {e}", exc_info=True)
                raise e

    async def get_metrics(self):
        """Get current sentiment percentage from Dextools"""
        if not self.browser:
            await self.setup_playwright()

        try:
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
                logger.info("Loading Dextools metrics")
                await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
                await ScrapeUtils.random_delay(random.uniform(3, 7))  # SPA needs time to hydrate

                # Simulate human-like mouse movements
                for _ in range(random.randint(2, 4)):
                    await page.mouse.move(
                        random.randint(0, 1000),
                        random.randint(0, 700)
                    )
                    await asyncio.sleep(random.uniform(0.1, 0.3))

                # Random scroll - Dextools often needs scrolling to load content
                await page.evaluate(f'window.scrollTo(0, {random.randint(200, 500)})')
                await asyncio.sleep(random.uniform(0.8, 1.5))
                
                # Target the sentiment percentage span directly
                percent_element = await page.query_selector('span.percent.buy-color')
                if percent_element:
                    # Move mouse naturally to element
                    box = await percent_element.bounding_box()
                    if box:
                        # First move to general area
                        await page.mouse.move(
                            box['x'] + random.randint(-50, 50),
                            box['y'] + random.randint(-50, 50)
                        )
                        await asyncio.sleep(random.uniform(0.1, 0.3))
                        # Then to specific element
                        await page.mouse.move(
                            box['x'] + random.randint(5, 20),
                            box['y'] + random.randint(5, 10)
                        )
                        await asyncio.sleep(random.uniform(0.2, 0.5))
                    
                    text = await percent_element.text_content()
                    try:
                        # Strip the % and whitespace, convert to float
                        value = float(text.strip().rstrip('%'))
                        logger.info(f"Found sentiment value: {value}%")
                        return value
                    except ValueError:
                        logger.warning(f"Could not convert '{text}' to float")
                else:
                    logger.warning("Could not find sentiment percentage element")
                
                return 0
                    
            except Exception as e:
                logger.error(f"Error during page processing: {e}", exc_info=True)
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
        """Create progress embed for Dextools raids"""
        embed = discord.Embed(
            title="🦎 Dextools Sentiment Challenge",
            description="Help boost the positive sentiment rating!",
            color=0x00FF00
        )
        
        percentage = (current_value/target_value*100) if target_value > 0 else 0
        progress_bar = self.create_progress_bar(current_value, target_value)
        
        status_emoji = "✅" if percentage >= 100 else "🔸" if percentage >= 75 else "🔹"
        
        embed.add_field(
            name="🚀 Positive Sentiment Progress",
            value=(
                f"{status_emoji} Progress: {progress_bar} {percentage:.1f}%\n"
                f"Current: **{current_value:.1f}%** / Target: **{target_value:.1f}%**"
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
            description="🔒 This channel is locked until the sentiment target is met! 🔒",
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
            
            await ScrapeUtils.random_delay(30)  # 30 seconds base with jitter

    @commands.command(name='raid_dextools')
    @commands.has_permissions(manage_channels=True)
    async def raid_dextools(self, ctx, *, targets):
        """Start a Dextools sentiment raid
        
        Usage: !raid_dextools sentiment:<target> [timeout:<minutes>]
        Example: !raid_dextools sentiment:85 timeout:30"""
        
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
                        value = float(value)
                        if metric == 'timeout':
                            timeout_minutes = max(1, min(120, int(value)))
                        elif metric == 'sentiment' and 0 <= value <= 100:
                            target_value = value
                    except ValueError:
                        continue
                        
                except Exception:
                    continue

            if target_value is None:
                await ctx.send("Please provide a valid sentiment target between 0 and 100 (e.g., `sentiment:85`)")
                return
            
            # Lock channel
            await self.lock_channel(ctx.channel)
            
            # Start monitoring
            await self.monitor_raid(ctx, target_value, timeout_minutes)
            
        except Exception as e:
            logger.error(f"Error in raid_dextools: {e}", exc_info=True)
            await ctx.send(f"Error: {str(e)}")
            await self.unlock_channel(ctx.channel)

    def cog_unload(self):
        if self.browser:
            asyncio.create_task(self.browser.close())

async def setup(bot):
    await bot.add_cog(DextoolsRaid(bot))