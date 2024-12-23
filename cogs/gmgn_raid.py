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
logger = logging.getLogger('tetsuo_bot.gmgn_raid')

class GmgnRaid(BaseRaid):
    def __init__(self, bot):
        super().__init__(bot)
        self.browser = None
        self.target_url = "https://gmgn.ai/sol/token/8i51XNNpGaKaj4G4nDdmQh95v4FKAxw8mhtaRoKd9tE8"
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
        """Get current sentiment percentage from GMGN.ai"""
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
                logger.info("Loading GMGN.ai metrics")
                await page.goto(self.target_url, wait_until="domcontentloaded", timeout=60000)
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
                
                # Handle the "Got it" popup more naturally
                try:
                    got_it_button = await page.wait_for_selector('text="Got it"', timeout=10000)
                    if got_it_button:
                        # Move mouse to button naturally
                        box = await got_it_button.bounding_box()
                        if box:
                            # Move to general area first
                            await page.mouse.move(
                                box['x'] + random.randint(-50, 50),
                                box['y'] + random.randint(-50, 50)
                            )
                            await asyncio.sleep(random.uniform(0.1, 0.3))
                            # Then to button
                            await page.mouse.move(
                                box['x'] + box['width']/2 + random.randint(-5, 5),
                                box['y'] + box['height']/2 + random.randint(-5, 5)
                            )
                            await asyncio.sleep(random.uniform(0.2, 0.4))
                            await got_it_button.click()
                            await ScrapeUtils.random_delay(random.uniform(1, 2))
                except Exception as e:
                    logger.debug(f"No Got it button found or error clicking it: {e}")
                
                # First check if we can find the image
                vote_img = await page.query_selector('img[src="/static/vote/vote2.png"]')
                if vote_img:
                    # Move mouse near image naturally
                    box = await vote_img.bounding_box()
                    if box:
                        await page.mouse.move(
                            box['x'] + random.randint(5, 20),
                            box['y'] + random.randint(5, 10)
                        )
                        await asyncio.sleep(random.uniform(0.2, 0.5))
                    
                    # Get image's parent element
                    parent = await vote_img.evaluate('node => node.parentElement')
                    if parent:
                        logger.debug("Found image parent element")
                    else:
                        logger.warning("Could not find image parent element")
                    
                    # Try to find the percentage div
                    text_elements = await page.query_selector('div:has(img[src="/static/vote/vote2.png"]) + div')
                    if text_elements:
                        # Move to text element
                        box = await text_elements.bounding_box()
                        if box:
                            await page.mouse.move(
                                box['x'] + random.randint(5, 20),
                                box['y'] + random.randint(5, 10)
                            )
                            await asyncio.sleep(random.uniform(0.2, 0.5))
                        
                        text = await text_elements.text_content()
                        try:
                            value = float(text.strip('%'))
                            logger.info(f"Successfully parsed value: {value}%")
                            return value
                        except ValueError:
                            logger.warning(f"Could not convert '{text}' to float")
                    else:
                        logger.warning("Could not find div after image")

                logger.warning("Could not find vote percentage")
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
        """Create progress embed for GMGN.ai raids"""
        embed = discord.Embed(
            title="🦎 GMGN.ai Sentiment Challenge",
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

    @commands.command(name='raid_gmgn')
    @commands.has_permissions(manage_channels=True)
    async def raid_gmgn(self, ctx, *, targets):
        """Start a GMGN.ai sentiment raid
        
        Usage: !raid_gmgn sentiment:<target> [timeout:<minutes>]
        Example: !raid_gmgn sentiment:85 timeout:30"""
        
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
            logger.error(f"Error in raid_gmgn: {e}", exc_info=True)
            await ctx.send(f"Error: {str(e)}")
            await self.unlock_channel(ctx.channel)

    def cog_unload(self):
        if self.browser:
            asyncio.create_task(self.browser.close())

async def setup(bot):
    await bot.add_cog(GmgnRaid(bot))