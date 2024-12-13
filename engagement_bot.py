import discord
from discord.ext import commands
import asyncio
from datetime import datetime
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import re

load_dotenv()

class EngagementBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.browser = None
        self.locked_channels = {}
        self.engagement_targets = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print('EngagementBot is ready')
        await self.setup_playwright()

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

    @commands.command(name='!raid')
    @commands.has_permissions(manage_channels=True)
    async def raid(self, ctx, tweet_url: str, *, targets):
        """Start a X/Twitter engagement challenge

        Usage: !raid <tweet_url> <targets>
        Example: !raid https://twitter.com/user/123 likes:100 retweets:50
        
        Available targets:
        • likes - number of likes to reach
        • retweets - number of retweets + quotes to reach
        • bookmarks - number of bookmarks to reach"""
        print(f"raid called with url: {tweet_url} and targets: {targets}")
        
        try:
            if not tweet_url.startswith('http'):
                tweet_url = f"https://{tweet_url}"
            
            target_dict = {}
            for pair in targets.split():
                try:
                    metric, value = pair.split(':')
                    if metric.lower() in ['likes', 'retweets', 'bookmarks']:
                        target_dict[metric.lower()] = int(value)
                except ValueError:
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

            await ctx.send(embed=lock_embed)
            
            # Send challenge message and store it
            embed = await self.create_progress_embed(tweet_url, target_dict)
            challenge_message = await ctx.send(embed=embed)
            
            self.engagement_targets[ctx.channel.id] = {
                'tweet_url': tweet_url,
                'targets': target_dict,
                'start_time': datetime.now(),
                'last_update': datetime.now(),
                'message_id': challenge_message.id
            }
            
            # Start monitoring
            self.bot.loop.create_task(self.monitor_engagement(ctx.channel, tweet_url, target_dict))
            
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
            percentage = (current/target*100) if target > 0 else 0
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
        
        embed.timestamp = datetime.now()
        embed.set_footer(text="Last updated")
        
        return embed

    async def monitor_engagement(self, channel, tweet_url, targets):
        while self.locked_channels.get(channel.id):
            try:
                metrics = await self.get_tweet_metrics(tweet_url)
                
                challenge_data = self.engagement_targets.get(channel.id)
                if not challenge_data:
                    break
                    
                time_since_update = datetime.now() - challenge_data['last_update']
                if time_since_update.total_seconds() < 15:
                    await asyncio.sleep(3)
                    continue
                
                challenge_data['last_update'] = datetime.now()
                
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
                    # Unlock channel
                    overwrites = channel.overwrites_for(channel.guild.default_role)
                    overwrites.send_messages = True
                    await channel.set_permissions(channel.guild.default_role, overwrite=overwrites)
                    
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

    @commands.command(name='!raid_stop')
    @commands.has_permissions(manage_channels=True)
    async def raid_stop(self, ctx):
        """End the current engagement challenge and unlock the channel"""
        if ctx.channel.id in self.locked_channels:
            overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
            overwrites.send_messages = True
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites)
            
            del self.locked_channels[ctx.channel.id]
            del self.engagement_targets[ctx.channel.id]
            
            await ctx.send("Challenge ended manually. Channel unlocked!")
        else:
            await ctx.send("No active challenge in this channel!")

    def cog_unload(self):
        if self.browser:
            asyncio.create_task(self.browser.close())

async def setup(bot):
    await bot.add_cog(EngagementBot(bot))
