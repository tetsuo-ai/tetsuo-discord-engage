from .base_raid import BaseRaid
import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import re
import json

load_dotenv()

class TwitterRaid(BaseRaid):
    def __init__(self, bot):
        super().__init__(bot)
        self.browser = None
        self.raid_history = []
        self.history_file = 'raid_history.json'
        self.load_raid_history()
        self.raid_channel_id = int(os.getenv('RAID_CHANNEL_ID', 0)) or None

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
            print(f"Error loading raid history: {e}")
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
            print(f"Error saving raid history: {e}")

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
        summary += "**RECENT RAIDS:**\n"

        # Add individual raid entries (most recent first)
        for raid in sorted(self.raid_history, key=lambda x: x['timestamp'], reverse=True):
            time_ago = self.format_time_ago(raid['timestamp'])
            status = "✅ SUCCESS - All targets met" if raid['success'] else "❌ TIMEOUT"
            
            if raid['progress']:
                progress_str = f" - Reached {max(raid['progress'].values()):.0f}% of targets"
                status += progress_str if not raid['success'] else ""
            
            summary += f"> 🔗 <{raid['tweet_url']}>\n"
            summary += f"> {status}\n"
            summary += f"> ⏰ Duration: {raid['duration']:.0f} minutes\n"
            summary += f"> 🕒 {time_ago}\n"
            summary += "\n"

        # Update or create pinned message
        if existing_summary:
            await existing_summary.edit(content=summary)
        else:
            new_summary = await channel.send(summary)
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
        print('TwitterRaid is ready')
        await self.setup_playwright()

    def cog_unload(self):
        if self.browser:
            asyncio.create_task(self.browser.close())
        self.raid_history.clear()

    async def setup_playwright(self):
        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            print("Playwright browser initialized successfully")
        except Exception as e:
            print(f"Error initializing Playwright: {e}")
            raise e

    async def get_tweet_metrics(self, tweet_url):
        print(f"Fetching metrics for tweet: {tweet_url}")
        tweet_url = tweet_url.replace('x.com', 'twitter.com')
        
        if not self.browser:
            await self.setup_playwright()

        try:
            context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = await context.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
            
            try:
                await page.goto(tweet_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(5)
                
                metrics = {
                    'likes': 0,
                    'retweets': 0,
                    'replies': 0,
                    'bookmarks': 0
                }

                metrics_group = await page.query_selector('div[role="group"]')
                if not metrics_group:
                    print("No metrics group found")
                    return metrics
                    
                metric_containers = await metrics_group.query_selector_all('[role="link"]')
                
                for container in metric_containers:
                    try:
                        number_element = await container.query_selector('[data-testid="app-text-transition-container"]')
                        if not number_element:
                            continue
                            
                        number_text = await number_element.inner_text()
                        
                        text = number_text.strip().upper()
                        try:
                            multiplier = 1
                            if text.endswith('K'):
                                multiplier = 1000
                                text = text[:-1]
                            elif text.endswith('M'):
                                multiplier = 1000000
                                text = text[:-1]
                                
                            number = float(text.replace(',', ''))
                            number = int(number * multiplier)
                        except (ValueError, TypeError):
                            number = 0
                        
                        href = await container.get_attribute('href') or ''
                        
                        if href:
                            print(f"Found metric - {href}: {number_text}")
                            if '/likes' in href:
                                metrics['likes'] = number
                            elif '/retweets' in href and 'with_comments' not in href:
                                metrics['retweets'] = number
                            elif '/with_comments' in href:
                                metrics['retweets'] += number
                        
                    except Exception as e:
                        print(f"Error processing metric element: {e}")
                        continue

                bookmark_container = await metrics_group.query_selector('div[dir="ltr"]:not([role="link"])')
                if bookmark_container:
                    number_element = await bookmark_container.query_selector('[data-testid="app-text-transition-container"]')
                    if number_element:
                        number_text = await number_element.inner_text()
                        text = number_text.strip().upper()
                        try:
                            multiplier = 1
                            if text.endswith('K'):
                                multiplier = 1000
                                text = text[:-1]
                            elif text.endswith('M'):
                                multiplier = 1000000
                                text = text[:-1]
                                
                            metrics['bookmarks'] = int(float(text.replace(',', '')) * multiplier)
                            print(f"Found metric - bookmarks: {number_text}")
                        except (ValueError, TypeError):
                            metrics['bookmarks'] = 0

                print(f"Final extracted metrics: {metrics}")
                return metrics
                    
            except Exception as e:
                print(f"Error during page load or metric extraction: {e}")
                
            finally:
                await page.close()
                await context.close()
                    
        except Exception as e:
            print(f"Error in get_tweet_metrics: {e}")
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
        Example: !raid https://twitter.com/user/123 likes:100 retweets:50 timeout:120
        
        Available targets:
        • likes - number of likes to reach
        • retweets - number of retweets + quotes to reach
        • bookmarks - number of bookmarks to reach
        • timeout - minutes until raid auto-ends (default: 15)"""
        if not await self.check_raid_channel(ctx):
            return
        print(f"raid called with url: {tweet_url} and targets: {targets}")
        
        try:
            # Validate tweet URL
            if not re.match(r'^https?://(twitter\.com|x\.com)/\w+/status/\d+$', tweet_url):
                await ctx.send("❌ Invalid tweet URL. Please provide a valid Twitter/X status URL.", delete_after=10)
                return

            # Parse and validate targets
            target_dict = {}
            timeout_minutes = 15  # Default timeout
            
            # Split on whitespace but ignore malformed input
            valid_metrics = {'likes', 'retweets', 'bookmarks', 'timeout'}
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
            lock_message = await ctx.send(embed=lock_embed)
            
            # Send challenge message and store it
            embed = await self.create_progress_embed(tweet_url, target_dict)
            challenge_message = await ctx.send(embed=embed)
            
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
            print(f"Error in start_engagement: {e}")
            await ctx.send(f"Error: {str(e)}")

    async def create_progress_embed(self, tweet_url, targets, metrics=None):
        if not metrics:
            metrics = await self.get_tweet_metrics(tweet_url)
            
        embed = discord.Embed(
            title="🎯 Community Engagement Challenge",
            description="Help support our community by engaging with this post!",
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
        print(f"Raid started at {start_time} with {timeout_minutes} minute timeout")
        
        while self.locked_channels.get(channel.id):
            try:
                current_time = datetime.now(timezone.utc)
                elapsed_minutes = (current_time - start_time).total_seconds() / 60
                print(f"Checking timeout: {elapsed_minutes:.2f} minutes elapsed of {timeout_minutes} allowed")
            
                if elapsed_minutes > timeout_minutes:
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

                    print(f"Timeout triggered after {elapsed_minutes:.2f} minutes")
                # Check for timeout
                if (datetime.now(timezone.utc) - start_time).total_seconds() > timeout_minutes * 60:
                    # Unlock channel
                    overwrites = channel.overwrites_for(channel.guild.default_role)
                    overwrites.send_messages = True
                    await channel.set_permissions(channel.guild.default_role, overwrite=overwrites)
                    
                    # Get the original message
                    challenge_data = self.engagement_targets.get(channel.id)
                    if challenge_data:
                        try:
                            # Delete lock message
                            try:
                                lock_message = await channel.fetch_message(challenge_data['lock_message_id'])
                                await lock_message.delete()
                            except:
                                print("Couldn't find lock message to delete")

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
                            print("Couldn't find original message for timeout update")
                    
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
                    print("Couldn't find original message")
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

                    # Unlock channel
                    overwrites = channel.overwrites_for(channel.guild.default_role)
                    overwrites.send_messages = True
                    await channel.set_permissions(channel.guild.default_role, overwrite=overwrites)
                    
                    # Delete lock message
                    try:
                        lock_message = await channel.fetch_message(challenge_data['lock_message_id'])
                        await lock_message.delete()
                    except:
                        print("Couldn't find lock message to delete")
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
                
            except Exception as e:
                print(f"Error monitoring engagement: {e}")
            
            await asyncio.sleep(30)

    def cog_unload(self):
        if self.browser:
            asyncio.create_task(self.browser.close())

async def setup(bot):
    await bot.add_cog(TwitterRaid(bot))
