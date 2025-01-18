from .base_raid import BaseRaid
import discord
from discord.ext import commands
from .telegram_utils import TelegramMessenger
import asyncio
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import re
import json
import random
from .scrape_utils import ScrapeUtils
import logging
logger = logging.getLogger('tetsuo_bot.twitter_raid')

load_dotenv()

class TwitterRaid(BaseRaid):
    def __init__(self, bot):
        super().__init__(bot)
        self.browser = None
        self.raid_history = []
        self.history_file = 'raid_history.json'
        self.load_raid_history()
        self.raid_channel_id = int(os.getenv('RAID_CHANNEL_ID', 0)) or None
        self.telegram = TelegramMessenger(
            os.getenv('TELEGRAM_BOT_TOKEN'),
            os.getenv('TELEGRAM_CHAT_ID')
        )
    
    async def setup_initial(self):
        """Initialize both Playwright and Telegram when cog is loaded"""
        try:
            await self.setup_playwright()
            if not await self.telegram.initialize():
                logger.error("Failed to initialize Telegram")
                return False
            logger.info("TwitterRaid: All components initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Error during TwitterRaid initialization: {e}", exc_info=True)
            return False

    def load_raid_history(self):
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    # Convert stored timestamps back to datetime objects
                    for raid in data:
                        raid['timestamp'] = datetime.fromisoformat(raid['timestamp'])
                    self.raid_history = data
                    # Clean up old entries on load
                    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
                    self.raid_history = [
                        raid for raid in self.raid_history 
                        if raid['timestamp'] > cutoff
                    ]
        except Exception as e:
            logger.error(f"Error loading raid history: {e}", exc_info=True)
            self.raid_history = []

    def save_raid_history(self):
        try:
            # Convert datetime objects to ISO format strings for JSON serialization
            history_data = []
            for raid in self.raid_history:
                raid_copy = raid.copy()
                raid_copy['timestamp'] = raid_copy['timestamp'].isoformat()
                history_data.append(raid_copy)
                
            with open(self.history_file, 'w') as f:
                json.dump(history_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving raid history: {e}", exc_info=True)

    async def update_raid_history(self, channel_id, tweet_url, success, duration_minutes, final_progress):
        if not self.raid_channel_id:
            self.raid_channel_id = channel_id
            
        if channel_id != self.raid_channel_id:
            return
            
        self.raid_history.append({
            'tweet_url': tweet_url,
            'success': success,
            'timestamp': datetime.now(timezone.utc),
            'duration': duration_minutes,
            'progress': final_progress
        })
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        self.raid_history = [
            raid for raid in self.raid_history 
            if raid['timestamp'] > cutoff
        ]
        
        self.save_raid_history()  # Save after updating
        await self.update_raid_summary()

    async def update_raid_summary(self):
        channel = self.bot.get_channel(self.raid_channel_id)
        if not channel:
            return

        # Find existing pinned summary or None
        existing_summary = None
        pins = await channel.pins()
        for message in pins:
            if message.author == self.bot.user and "RAID PERFORMANCE SUMMARY" in message.content:
                existing_summary = message
                break

        # Get raids from last 24h
        if not self.raid_history:
            if existing_summary:
                await existing_summary.delete()
            return

        # Calculate statistics
        total_raids = len(self.raid_history)
        successful_raids = sum(1 for raid in self.raid_history if raid['success'])
        
        # Create summary message
        summary = "📊 **RAID PERFORMANCE SUMMARY (24h)**\n"
        summary += f"> Total Raids: {total_raids} | Successful: {successful_raids} | "
        summary += f"Timeouts: {total_raids - successful_raids}\n\n"
        
        if total_raids > 0:
            summary += "**RECENT RAIDS:**\n"
            
            # Show only the 10 most recent raids
            recent_raids = sorted(self.raid_history, key=lambda x: x['timestamp'], reverse=True)[:10]
            shown_raids = len(recent_raids)
            
            for raid in recent_raids:
                time_ago = self.format_time_ago(raid['timestamp'])
                status = "✅ SUCCESS" if raid['success'] else "❌ TIMEOUT"
                
                if not raid['success'] and raid['progress']:
                    status += f" ({max(raid['progress'].values()):.0f}%)"
                
                # Truncate URL if needed
                url = raid['tweet_url']
                if len(url) > 60:  # Arbitrary length that looks good
                    url = url[:57] + "..."
                
                summary += f"> 🔗 {url}\n"
                summary += f"> {status} • {raid['duration']:.0f}m • {time_ago}\n"
                summary += "\n"
            
            # Add note about additional raids if any were omitted
            if shown_raids < total_raids:
                summary += f"*...and {total_raids - shown_raids} more raids in the last 24h*"

        # Update or create pinned message
        try:
            if existing_summary:
                await existing_summary.edit(content=summary)
            else:
                new_summary = await channel.send(summary)
                await new_summary.pin()
        except discord.errors.HTTPException as e:
            logger.error(f"Failed to update raid summary (len={len(summary)}): {e}")
            # Fallback to a more compact format if still too long
            if "Must be 4000 or fewer in length" in str(e):
                compact_summary = f"📊 **RAID PERFORMANCE SUMMARY (24h)**\n"
                compact_summary += f"> Total Raids: {total_raids} | Successful: {successful_raids} | "
                compact_summary += f"Timeouts: {total_raids - successful_raids}\n\n"
                compact_summary += "*Summary truncated due to length. Check raid history for details.*"
                
                if existing_summary:
                    await existing_summary.edit(content=compact_summary)
                else:
                    new_summary = await channel.send(compact_summary)
                    await new_summary.pin()

    def format_time_ago(self, timestamp):
        delta = datetime.now(timezone.utc) - timestamp
        hours = delta.total_seconds() / 3600
        
        if hours < 1:
            minutes = delta.total_seconds() / 60
            return f"{minutes:.0f} minutes ago"
        elif hours < 24:
            return f"{hours:.0f} hours ago"
        else:
            return f"{hours/24:.0f} days ago"

    @commands.Cog.listener()
    async def on_ready(self):
        await self.setup_playwright()

    def cog_unload(self):
        if self.browser:
            asyncio.create_task(self.browser.close())
        asyncio.create_task(self.telegram.cleanup())
        self.raid_history.clear()

    async def setup_playwright(self):
        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
        except Exception as e:
            logger.error(f"Error initializing Playwright: {e}", exc_info=True)
            raise e

    async def get_tweet_metrics(self, tweet_url):
        logger.info(f"Fetching metrics for tweet: {tweet_url}")
        tweet_url = tweet_url.replace('x.com', 'twitter.com')
        
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
                await page.goto(tweet_url, wait_until="domcontentloaded", timeout=10000)
                await ScrapeUtils.random_delay(random.uniform(2, 3))
                
                # Simulate human-like mouse movements
                for _ in range(random.randint(1, 2)):
                    await page.mouse.move(
                        random.randint(0, 1000),
                        random.randint(0, 700)
                    )
                    await asyncio.sleep(random.uniform(0.1, 0.3))

                # Random scroll - Twitter often needs it
                await page.evaluate(f'window.scrollTo(0, {random.randint(100, 400)})')
                await asyncio.sleep(random.uniform(0.25, 0.75))
                
                # Handle the notifications popup with human-like interaction
                try:
                    notification_button = await page.wait_for_selector('div[role="button"]:has-text("Not now")', timeout=5000)
                    if notification_button:
                        logger.debug("Found notifications popup, dismissing...")
                        box = await notification_button.bounding_box()
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
                            await notification_button.click()
                            await ScrapeUtils.random_delay(random.uniform(1, 2))
                except Exception as e:
                    logger.debug(f"No notifications popup or error handling it: {e}")
                
                metrics = {
                    'likes': 0,
                    'retweets': 0,
                    'replies': 0,
                    'bookmarks': 0
                }

                try:
                    metrics_group = await page.query_selector('div[role="group"][aria-label*="replies"]')
                    if not metrics_group:
                        logger.warning("No metrics group found")
                        return metrics
                        
                    # Find all buttons with data-testid attributes and their text content
                    for button_type in ['like', 'retweet', 'reply', 'bookmark']:
                        try:
                            button = await page.query_selector(f'button[data-testid="{button_type}"]')
                            if not button:
                                logger.debug(f"No {button_type} button found")
                                continue

                            text = await button.evaluate('el => el.textContent')
                            if not text.strip():
                                logger.debug(f"Empty {button_type} count text")
                                continue
                            logger.debug(f"Found {button_type} count: {text}")
                            
                            # Clean and parse the number
                            try:
                                text = text.strip().replace(',', '')
                                if 'K' in text.upper():
                                    number = float(text.upper().replace('K', '')) * 1000
                                elif 'M' in text.upper():
                                    number = float(text.upper().replace('M', '')) * 1000000
                                else:
                                    number = float(text)
                                    
                                if button_type == 'reply':
                                    metrics['replies'] = int(number)
                                else:
                                    metrics[f"{button_type}s"] = int(number)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Could not parse {button_type} count: {text} - Error: {e}")
                                
                        except Exception as e:
                            logger.error(f"Error processing {button_type} metric: {e}", exc_info=True)
                            continue
                            
                except Exception as e:
                    logger.error(f"Error during metrics extraction: {e}", exc_info=True)
                    
                return metrics
                    
            except Exception as e:
                logger.error(f"Error during page load or metric extraction: {e}", exc_info=True)
                
            finally:
                if 'page' in locals():
                    await page.close()
                if 'context' in locals():
                    await context.close()
                    
        except Exception as e:
            logger.error(f"Error in get_tweet_metrics: {e}", exc_info=True)
            if 'page' in locals():
                await page.close()
            if 'context' in locals():
                await context.close()
            return {
                'likes': 0,
                'retweets': 0,
                'replies': 0,
                'bookmarks': 0
            }
        
    def create_progress_bar(self, current, target, length=20):
        percentage = min(current/target if target > 0 else 0, 1)
        filled = int(length * percentage)
        return f"[{'='*filled}{'-'*(length-filled)}]"

    @commands.command(name='raid')
    @commands.has_permissions(manage_channels=True)
    async def raid(self, ctx, tweet_url: str, *, targets):
        """Start a X/Twitter engagement challenge

        Usage: !raid <tweet_url> <targets>
        Example: !raid https://twitter.com/user/123 likes:100 retweets:50 replies:25 timeout:120
        
        Available targets:
        • likes - number of likes to reach
        • retweets - number of retweets + quotes to reach
        • replies - number of replies to reach
        • bookmarks - number of bookmarks to reach
        • timeout - minutes until raid auto-ends (default: 15)"""
        if not await self.check_raid_channel(ctx):
            return
        logger.debug(f"raid called with url: {tweet_url} and targets: {targets}")
        
        try:
            # Clean and validate tweet URL
            tweet_url = re.match(r'^https?://(twitter\.com|x\.com)/\w+/status/\d+', tweet_url)
            if not tweet_url:
                await ctx.send("❌ Invalid tweet URL. Please provide a valid Twitter/X status URL.", delete_after=10)
                return
                
            tweet_url = tweet_url.group(0).replace('x.com', 'twitter.com')  # Use clean URL
            logger.debug(f"Cleaned URL: {tweet_url}")

            # Parse and validate targets
            target_dict = {}
            timeout_minutes = 15  # Default timeout
            
            # Split on whitespace but ignore malformed input
            valid_metrics = {'likes', 'retweets', 'bookmarks', 'replies', 'timeout'}
            for pair in targets.split():
                try:
                    if ':' not in pair:
                        continue
                        
                    metric, value = pair.split(':', 1)
                    metric = metric.lower()
                    
                    if metric not in valid_metrics:
                        continue
                    
                    # Validate value is a positive integer
                    try:
                        value = int(value)
                        if metric == 'timeout':
                            # Timeout: 1-120 minutes
                            timeout_minutes = max(1, min(120, value))
                        elif value > 0 and value <= 1000000:  # Reasonable max value
                            target_dict[metric] = value
                    except ValueError:
                        continue
                        
                except Exception:
                    continue
            
            if not target_dict:
                await ctx.send("Please provide valid targets (e.g., `likes:100 retweets:50`)")
                return
            
            if ctx.channel.id in self.locked_channels:
                await ctx.send("There's already an active raid in this channel!")
                return
            
            # Get initial metrics once
            initial_metrics = await self.get_tweet_metrics(tweet_url)

            # Lock the channel
            overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
            overwrites.send_messages = False
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
            
            self.locked_channels[ctx.channel.id] = True
            
            # Send initial lock message
            lock_embed = discord.Embed(
                title="🚨 CHANNEL LOCKED 🚨",
                description="🔒 This channel is locked until all engagement targets are met! 🔒",
                color=0xFF0000  # Bright red
            )
            lock_embed.set_footer(text="Channel will automatically unlock when targets are reached")
            lock_message = await ctx.send(content=self.raid_mention, embed=lock_embed)

            # Send Discord challenge message and store it 
            embed = await self.create_progress_embed(tweet_url, target_dict, initial_metrics)
            challenge_message = await ctx.send(embed=embed)

            # Send initial Telegram message with metrics
            await self.telegram.lock_chat()
            await self.telegram.send_raid_message(tweet_url, target_dict, initial_metrics)
            
            self.engagement_targets[ctx.channel.id] = {
                'tweet_url': tweet_url,
                'targets': target_dict,
                'start_time': datetime.now(timezone.utc),
                'last_update': datetime.now(timezone.utc),
                'message_id': challenge_message.id,
                'lock_message_id': lock_message.id,
                'timeout': timeout_minutes
            }
            
            # Start monitoring
            self.bot.loop.create_task(self.monitor_engagement(ctx.channel, tweet_url, target_dict, timeout_minutes))
            
        except Exception as e:
            logger.error(f"Error in start_engagement: {e}", exc_info=True)
            await ctx.send(f"Error: {str(e)}")

    async def create_progress_embed(self, tweet_url, targets, metrics=None):
        if not metrics:
            metrics = await self.get_tweet_metrics(tweet_url)
            
        embed = discord.Embed(
            title="🎯 Community Engagement Challenge 🎯",
            color=0x1DA1F2
        )
        
        for metric, target in targets.items():
            current = metrics.get(metric, 0)
            percentage = (current/target*100) if target > 0 else 100
            progress_bar = self.create_progress_bar(current, target)
            
            status_emoji = "✅" if percentage >= 100 else "🔸" if percentage >= 75 else "🔹" if percentage >= 50 else "⭕"
            
            metric_emoji = {
                'likes': '❤️',
                'retweets': '🔄',
                'replies': '💬',
                'bookmarks': '🔖',
                'quotes': '💭'
            }.get(metric, '📊')
            
            field_value = (
                f"{status_emoji} Progress: {progress_bar} {percentage:.1f}%\n"
                f"Current: **{current}** / Target: **{target}**"
            )
            
            embed.add_field(
                name=f"{metric_emoji} {metric.title()}",
                value=field_value,
                inline=False
            )
        
        embed.add_field(
            name="📝 Original Post",
            value=f"[Click to view tweet]({tweet_url})",
            inline=False
        )
        
        embed.timestamp = datetime.now(timezone.utc)
        embed.set_footer(text="Last updated")
        
        return embed

    async def monitor_engagement(self, channel, tweet_url, targets, timeout_minutes):
        start_time = datetime.now(timezone.utc)
        logger.debug(f"Raid started at {start_time} with {timeout_minutes} minute timeout")
        # Get initial metrics
        metrics = await self.get_tweet_metrics(tweet_url)

        while self.locked_channels.get(channel.id):
            try:
                current_time = datetime.now(timezone.utc)
                elapsed_minutes = (current_time - start_time).total_seconds() / 60
                logger.debug(f"Checking timeout: {elapsed_minutes:.2f} minutes elapsed of {timeout_minutes} allowed")
            
                if (datetime.now(timezone.utc) - start_time).total_seconds() > timeout_minutes * 60:
                    # Calculate progress percentages
                    progress_percentages = {
                        metric: (metrics.get(metric, 0) / target * 100) if target > 0 else 100 
                        for metric, target in targets.items()
                    }
                    
                    # Update raid history
                    await self.update_raid_history(
                        channel.id,
                        tweet_url,
                        success=False,
                        duration_minutes=timeout_minutes,
                        final_progress=progress_percentages
                    )

                    logger.debug(f"Timeout triggered after {elapsed_minutes:.2f} minutes")
                # Check for timeout
                if (datetime.now(timezone.utc) - start_time).total_seconds() > timeout_minutes * 60:
                    # Unlock channel
                    overwrites = channel.overwrites_for(channel.guild.default_role)
                    overwrites.send_messages = True
                    await channel.set_permissions(channel.guild.default_role, overwrite=overwrites)
                    await self.telegram.unlock_chat()
                    
                    # Get the original message
                    challenge_data = self.engagement_targets.get(channel.id)
                    if challenge_data:
                        try:
                            # Delete lock message
                            try:
                                lock_message = await channel.fetch_message(challenge_data['lock_message_id'])
                                await lock_message.delete()
                            except:
                                logger.debug("Lock message already deleted")

                            message = await channel.fetch_message(challenge_data['message_id'])
                            metrics = await self.get_tweet_metrics(tweet_url)
                            
                            # Create timeout embed
                            timeout_embed = await self.create_progress_embed(tweet_url, targets, metrics)
                            timeout_embed.color = 0xFF6B6B  # Soft red
                            
                            # Add timeout message
                            timeout_embed.add_field(
                                name="\u200b",
                                value="\u200b",
                                inline=False
                            )
                            timeout_embed.add_field(
                                name="⏰ RAID TIMED OUT! ⏰",
                                value=f"```diff\n- Raid ended after {timeout_minutes} minutes! Channel unlocked! 🔓\n```",
                                inline=False
                            )
                            
                            await message.edit(embed=timeout_embed)
                        except:
                            logger.warning("Could not find original message for timeout update")
                    
                    del self.locked_channels[channel.id]
                    del self.engagement_targets[channel.id]
                    return

                metrics = await self.get_tweet_metrics(tweet_url)
                
                challenge_data = self.engagement_targets.get(channel.id)
                if not challenge_data:
                    break
                    
                time_since_update = datetime.now(timezone.utc) - challenge_data['last_update']
                if time_since_update.total_seconds() < 15:
                    await asyncio.sleep(3)
                    continue
                
                challenge_data['last_update'] = datetime.now(timezone.utc)
                
                # Get the original message
                try:
                    message = await channel.fetch_message(challenge_data['message_id'])
                except:
                    logger.warning("Could not find original message")
                    break
                
                # Check if ALL targets are met
                all_met = True
                for metric, target in targets.items():
                    if metrics.get(metric, 0) < target:
                        all_met = False
                        break
                
                if all_met:
                    # Calculate duration
                    duration = (datetime.now(timezone.utc) - start_time).total_seconds() / 60
                    
                    # Update raid history
                    progress_percentages = {
                        metric: (metrics.get(metric, 0) / target * 100) 
                        for metric, target in targets.items()
                    }
                    await self.update_raid_history(
                        channel.id,
                        tweet_url,
                        success=True,
                        duration_minutes=duration,
                        final_progress=progress_percentages
                    )

                    await self.telegram.update_progress(metrics, targets, tweet_url)

                    # Unlock channel
                    overwrites = channel.overwrites_for(channel.guild.default_role)
                    overwrites.send_messages = True
                    await channel.set_permissions(channel.guild.default_role, overwrite=overwrites)
                    await self.telegram.unlock_chat()
                    
                    # Delete lock message
                    try:
                        lock_message = await channel.fetch_message(challenge_data['lock_message_id'])
                        await lock_message.delete()
                    except:
                        logger.debug("Couldn't find lock message to delete")
                    # Update progress message with completion
                    final_embed = await self.create_progress_embed(tweet_url, targets, metrics)
                    final_embed.color = 0x00FF00  # Bright green

                    # Add completion banner at the bottom
                    final_embed.add_field(
                        name="\u200b",  # Invisible separator
                        value="\u200b",
                        inline=False
                    )
                    final_embed.add_field(
                        name="🎉 CHALLENGE COMPLETE! 🎉",
                        value="```diff\n+ All targets reached! Channel unlocked! 🔓\n```",
                        inline=False
                    )
                    
                    await message.edit(embed=final_embed)
                    
                    del self.locked_channels[channel.id]
                    del self.engagement_targets[channel.id]
                    break
                else:
                    # Update progress
                    embed = await self.create_progress_embed(tweet_url, targets, metrics)
                    await message.edit(embed=embed)
                    
                    # Update Telegram progress
                    await self.telegram.update_progress(metrics, targets, tweet_url)
                
                
            except Exception as e:
                logger.error(f"Error monitoring engagement: {e}", exc_info=True)
            
            await ScrapeUtils.random_delay(30)  # 30 seconds base with jitter

    def cog_unload(self):
        if self.browser:
            asyncio.create_task(self.browser.close())

async def setup(bot):
    cog = TwitterRaid(bot)
    if not await cog.setup_initial():  # Add this method
        logger.error("Failed to initialize TwitterRaid cog")
        return
    await bot.add_cog(cog)