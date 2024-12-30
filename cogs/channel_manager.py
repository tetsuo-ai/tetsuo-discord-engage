import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from datetime import datetime, timezone, timedelta
import logging
logger = logging.getLogger('tetsuo_bot.channel_manager')

class ChannelManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.raid_channel_id = int(os.getenv('RAID_CHANNEL_ID', 0)) or None
        self.last_metrics_update = None
        self.metrics_message_id = None
        self.previous_metrics = {
            'cmc_likes': None,
            'gecko_sentiment': None
        }
        self.cleanup_task = None
        self.metrics_task = None

    async def cleanup_messages(self):
        while True:
            try:
                if not self.raid_channel_id:
                    await asyncio.sleep(30)
                    continue
                    
                channel = self.bot.get_channel(self.raid_channel_id)
                if not channel:
                    await asyncio.sleep(30)
                    continue
                    
                try:
                    current_time = datetime.now(timezone.utc)
                    async for message in channel.history(limit=None):
                        # Skip pinned messages
                        if message.pinned:
                            continue
                            
                        # Calculate message age
                        message_age = (current_time - message.created_at).total_seconds()
                        
                        # Bot messages: Delete if older than 8 hours
                        if message.author.bot:
                            if message_age > (15 * 60):  # 15 minutes in seconds
                                await message.delete()
                                logger.debug("Deleted bot message")
                        # Non-bot messages: Delete if older than 15 minutes
                        else:
                            if message_age > (15 * 60):  # 15 minutes in seconds
                                await message.delete()
                                logger.debug("Deleted user message")
                                
                        # Add a small delay to avoid rate limits
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    logger.error(f"Error cleaning messages in raid channel: {e}", exc_info=True)
                    
                # Run cleanup every 5 minutes
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retrying if there's an error

    def get_trend_indicator(self, current, previous):
        if previous is None:
            return "➖"  # First reading
        elif current > previous:
            return "↗️"  # Increasing
        elif current < previous:
            return "↘️"  # Decreasing
        else:
            return "➖"  # No change
        
    async def update_metrics_dashboard(self):
        while True:
            try:
                if not self.raid_channel_id:
                    await asyncio.sleep(300)
                    continue

                channel = self.bot.get_channel(self.raid_channel_id)
                if not channel:
                    await asyncio.sleep(300)
                    continue

                # Get our raid cogs
                cmc_raid = self.bot.get_cog('CMCRaid')
                gecko_raid = self.bot.get_cog('GeckoRaid')
                gmgn_raid = self.bot.get_cog('GmgnRaid')
                dextools_raid = self.bot.get_cog('DextoolsRaid')

                if not cmc_raid or not gecko_raid or not gmgn_raid or not dextools_raid:
                    await asyncio.sleep(300)
                    continue

                # Fetch metrics
                cmc_likes = await cmc_raid.get_metrics()
                gecko_sentiment = await gecko_raid.get_metrics()
                gmgn_sentiment = await gmgn_raid.get_metrics()
                dextools_sentiment = await dextools_raid.get_metrics()

                # Get trend indicators
                cmc_trend = self.get_trend_indicator(cmc_likes, self.previous_metrics['cmc_likes'])
                gecko_trend = self.get_trend_indicator(gecko_sentiment, self.previous_metrics['gecko_sentiment'])
                gmgn_trend = self.get_trend_indicator(gmgn_sentiment, self.previous_metrics.get('gmgn_sentiment'))
                dextools_trend = self.get_trend_indicator(dextools_sentiment, self.previous_metrics.get('dextools_sentiment'))

                # Store current values as previous for next update
                self.previous_metrics['cmc_likes'] = cmc_likes
                self.previous_metrics['gecko_sentiment'] = gecko_sentiment
                self.previous_metrics['gmgn_sentiment'] = gmgn_sentiment
                self.previous_metrics['dextools_sentiment'] = dextools_sentiment

                # Create metrics embed
                embed = discord.Embed(
                    title="📊 **LIVE SENTIMENT METRICS**",
                    color=0x1DA1F2,
                    timestamp=datetime.now(timezone.utc)
                )

                # Add fields with metrics AND LINKS!
                embed.add_field(
                    name="**CoinMarketCap**",
                    value=(
                        f"Upvotes: **{cmc_likes}** {cmc_trend}\n"
                        "[View/Vote](https://coinmarketcap.com/dexscan/solana/2KB3i5uLKhUcjUwq3poxHpuGGqBWYwtTk5eG9E5WnLG6)"
                    ),
                    inline=False
                )

                # Add separator
                embed.add_field(name="\u200b", value="\u200b", inline=False)
                embed.add_field(
                    name="**GeckoTerminal**",
                    value=(
                        f"Sentiment: **{gecko_sentiment:.1f}%** {gecko_trend}\n"
                        "[View/Vote](https://www.geckoterminal.com/solana/pools/2KB3i5uLKhUcjUwq3poxHpuGGqBWYwtTk5eG9E5WnLG6)"
                    ),
                    inline=False
                )

                # Add separator
                embed.add_field(name="\u200b", value="\u200b", inline=False)
                embed.add_field(
                    name="**GMGN.ai**",
                    value=(
                        f"Sentiment: **{gmgn_sentiment:.1f}%** {gmgn_trend}\n"
                        "[View/Vote](https://gmgn.ai/sol/token/8i51XNNpGaKaj4G4nDdmQh95v4FKAxw8mhtaRoKd9tE8)"
                    ),
                    inline=False
                )

                # Add separator and Dextools
                embed.add_field(name="\u200b", value="\u200b", inline=False)
                embed.add_field(
                    name="**Dextools**",
                    value=(
                        f"Sentiment: **{dextools_sentiment:.1f}%** {dextools_trend}\n"
                        "[View/Vote](https://www.dextools.io/app/en/solana/pair-explorer/2KB3i5uLKhUcjUwq3poxHpuGGqBWYwtTk5eG9E5WnLG6)"
                    ),
                    inline=False
                )

                if self.previous_metrics['cmc_likes'] is not None:
                    changes = []
                    cmc_change = cmc_likes - self.previous_metrics['cmc_likes']
                    gecko_change = gecko_sentiment - self.previous_metrics['gecko_sentiment']
                    gmgn_change = gmgn_sentiment - self.previous_metrics['gmgn_sentiment']
                    dextools_change = dextools_sentiment - self.previous_metrics['dextools_sentiment']
                    
                    if cmc_change != 0:
                        changes.append(f"CMC: {'+'if cmc_change>0 else ''}{cmc_change} votes")
                    if gecko_change != 0:
                        changes.append(f"Gecko: {'+'if gecko_change>0 else ''}{gecko_change:.1f}%")
                    if gmgn_change != 0:
                        changes.append(f"GMGN: {'+'if gmgn_change>0 else ''}{gmgn_change:.1f}%")
                    if dextools_change != 0:
                        changes.append(f"Dextools: {'+'if dextools_change>0 else ''}{dextools_change:.1f}%")
                    
                    if changes:
                        embed.add_field(
                            name="Changes (5m)",
                            value="\n".join(changes),
                            inline=False
                        )

                embed.set_footer(text="Last updated")

                # Find and update existing metrics message
                if not self.metrics_message_id:
                    # Look for existing metrics message in pins
                    pins = await channel.pins()
                    for pin in pins:
                        if (pin.author == self.bot.user and 
                            pin.embeds and 
                            "📊 **LIVE SENTIMENT METRICS**" in pin.embeds[0].title):
                            self.metrics_message_id = pin.id
                            break

                try:
                    if self.metrics_message_id:
                        # Try to update existing message
                        message = await channel.fetch_message(self.metrics_message_id)
                        await message.edit(embed=embed)
                    else:
                        # Create new message if none exists
                        message = await channel.send(embed=embed)
                        await message.pin()
                        self.metrics_message_id = message.id
                except discord.NotFound:
                    # Message was deleted, create new one
                    message = await channel.send(embed=embed)
                    await message.pin()
                    self.metrics_message_id = message.id
                except Exception as e:
                    logger.warning(f"Error updating metrics message: {e}")
                    self.metrics_message_id = None  # Reset ID on error

            except Exception as e:
                logger.warning(f"Error in metrics dashboard task: {e}")

            # Update every 5 minutes
            await asyncio.sleep(300)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info('ChannelManager is ready')
        if self.cleanup_task:
            self.cleanup_task.cancel()
        if self.metrics_task:
            self.metrics_task.cancel()
            
        self.cleanup_task = self.bot.loop.create_task(self.cleanup_messages())
        self.metrics_task = self.bot.loop.create_task(self.update_metrics_dashboard())
        logger.info('ChannelManager tasks started')

    def cog_unload(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()
        if self.metrics_task:
            self.metrics_task.cancel()

    async def check_raid_channel(self, ctx):
        """Check if the command is being used in the designated raid channel"""
        if not self.raid_channel_id:
            await ctx.send("❌ No raid channel has been set! An administrator must use !set_raid_channel first.", delete_after=10)
            return False
        
        if ctx.channel.id != self.raid_channel_id:
            await ctx.send("❌ This command can only be used in the designated raid channel.", delete_after=10)
            return False
            
        return True

    @commands.command(name='raid_channel')
    @commands.has_permissions(manage_channels=True)
    async def raid_channel(self, ctx):
        """Display information about the current raid channel"""
        if not self.raid_channel_id:
            await ctx.send("❌ No raid channel has been set! An administrator must use !set_raid_channel to configure one.", delete_after=30)
            return
            
        channel = self.bot.get_channel(self.raid_channel_id)
        if not channel:
            await ctx.send("⚠️ Configured raid channel not found! The channel may have been deleted.", delete_after=30)
            return
            
        embed = discord.Embed(
            title="🎯 Raid Channel Configuration",
            color=0x00FF00
        )
        
        embed.add_field(
            name="Current Raid Channel",
            value=f"#{channel.name} (`{channel.id}`)",
            inline=False
        )
        
        if ctx.channel.id == self.raid_channel_id:
            embed.add_field(
                name="Status",
                value="✅ You are in the raid channel",
                inline=False
            )
        else:
            embed.add_field(
                name="Status",
                value=f"ℹ️ Raid channel is <#{self.raid_channel_id}>",
                inline=False
            )
            
        await ctx.send(embed=embed, delete_after=30)

    @commands.command(name='set_raid_channel')
    @commands.has_permissions(administrator=True) 
    async def set_raid_channel(self, ctx, channel_id: str):
        """Set the raid channel by ID"""
        try:
            self.raid_channel_id = int(channel_id)
            
            # Update environment
            env_path = '.env'
            existing_lines = []
            updated = False
            
            if os.path.exists(env_path):
                with open(env_path, 'r') as file:
                    existing_lines = file.readlines()
                    
                for i, line in enumerate(existing_lines):
                    if line.strip().startswith('RAID_CHANNEL_ID='):
                        existing_lines[i] = f'RAID_CHANNEL_ID={channel_id}\n'
                        updated = True
                        break
                
                if not updated:
                    existing_lines.append(f'RAID_CHANNEL_ID={channel_id}\n')
            else:
                existing_lines = [f'RAID_CHANNEL_ID={channel_id}\n']
            
            with open(env_path, 'w') as file:
                file.writelines(existing_lines)
            
            os.environ['RAID_CHANNEL_ID'] = channel_id
            
            # Update other cogs
            for cog_name in ['TwitterRaid', 'CMCRaid', 'GeckoRaid', 'GmgnRaid', 'DextoolsRaid']:
                if cog := self.bot.get_cog(cog_name):
                    cog.raid_channel_id = self.raid_channel_id
            
            await ctx.send(f"✅ Channel ID {channel_id} has been set as the raid channel.", delete_after=30)
                
        except ValueError:
            await ctx.send("❌ Please provide a valid channel ID", delete_after=10)
        except Exception as e:
            logger.error(f"Error setting raid channel: {e}", exc_info=True)
            await ctx.send(f"❌ Error setting raid channel: {str(e)}", delete_after=30)

    @commands.command(name='raid_stop')
    @commands.has_permissions(manage_channels=True)
    async def raid_stop(self, ctx):
        """End the current engagement challenge and unlock the channel"""
        if not await self.check_raid_channel(ctx):
            return

        # Get the active raids from both raid cogs
        twitter_raid = self.bot.get_cog('TwitterRaid')
        cmc_raid = self.bot.get_cog('CMCRaid')
        gecko_raid = self.bot.get_cog('GeckoRaid')
        gmgn_raid = self.bot.get_cog('GmgnRaid')
        dextools_raid = self.bot.get_cog('DextoolsRaid')
        
        channel_locked = False
        
        # Check TwitterRaid
        if twitter_raid and ctx.channel.id in twitter_raid.locked_channels:
            try:
                challenge_data = twitter_raid.engagement_targets.get(ctx.channel.id)
                if challenge_data:
                    try:
                        # Delete lock message
                        lock_message = await ctx.channel.fetch_message(challenge_data['lock_message_id'])
                        if lock_message:
                            await lock_message.delete()
                    except discord.NotFound:
                        logger.debug("Lock message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting lock message: {e}", exc_info=True)
                        
                    try:
                        # Delete progress message
                        progress_message = await ctx.channel.fetch_message(challenge_data['message_id'])
                        if progress_message:
                            await progress_message.delete()
                    except discord.NotFound:
                        logger.debug("Progress message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting progress message: {e}", exc_info=True)

                # Unlock Discord Channel
                await twitter_raid.unlock_channel(ctx.channel)

                # Unlock Telegram chat and delete message
                try:
                    if twitter_raid.telegram.current_message_id:
                        await twitter_raid.telegram.delete_message(twitter_raid.telegram.current_message_id)
                    await twitter_raid.telegram.unlock_chat()
                except Exception as e:
                    logger.error(f"Error cleaning up Telegram: {e}", exc_info=True)

                channel_locked = True
                
            except Exception as e:
                logger.error(f"Error in raid_stop (Twitter): {e}", exc_info=True)
                
        # Check CMCRaid
        if cmc_raid and ctx.channel.id in cmc_raid.locked_channels:
            try:
                challenge_data = cmc_raid.engagement_targets.get(ctx.channel.id)
                if challenge_data:
                    try:
                        # Delete lock message
                        lock_message = await ctx.channel.fetch_message(challenge_data['lock_message_id'])
                        if lock_message:
                            await lock_message.delete()
                    except discord.NotFound:
                        logger.debug("Lock message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting lock message: {e}", exc_info=True)
                        
                    try:
                        # Delete progress message
                        progress_message = await ctx.channel.fetch_message(challenge_data['message_id'])
                        if progress_message:
                            await progress_message.delete()
                    except discord.NotFound:
                        logger.debug("Progress message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting progress message: {e}", exc_info=True)

                await cmc_raid.unlock_channel(ctx.channel)
                channel_locked = True
                
            except Exception as e:
                logger.error(f"Error in raid_stop (CMC): {e}", exc_info=True)

        # Add Gecko check
        if gecko_raid and ctx.channel.id in gecko_raid.locked_channels:
            try:
                challenge_data = gecko_raid.engagement_targets.get(ctx.channel.id)
                if challenge_data:
                    try:
                        lock_message = await ctx.channel.fetch_message(challenge_data['lock_message_id'])
                        if lock_message:
                            await lock_message.delete()
                    except discord.NotFound:
                        logger.debug("Lock message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting lock message: {e}", exc_info=True)
                        
                    try:
                        progress_message = await ctx.channel.fetch_message(challenge_data['message_id'])
                        if progress_message:
                            await progress_message.delete()
                    except discord.NotFound:
                        logger.debug("Progress message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting progress message: {e}", exc_info=True)

                await gecko_raid.unlock_channel(ctx.channel)
                channel_locked = True
                
            except Exception as e:
                logger.error(f"Error in raid_stop (Gecko): {e}", exc_info=True)

        # Add GMGN check
        if gmgn_raid and ctx.channel.id in gmgn_raid.locked_channels:
            try:
                challenge_data = gmgn_raid.engagement_targets.get(ctx.channel.id)
                if challenge_data:
                    try:
                        lock_message = await ctx.channel.fetch_message(challenge_data['lock_message_id'])
                        if lock_message:
                            await lock_message.delete()
                    except discord.NotFound:
                        logger.debug("Lock message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting lock message: {e}", exc_info=True)
                        
                    try:
                        progress_message = await ctx.channel.fetch_message(challenge_data['message_id'])
                        if progress_message:
                            await progress_message.delete()
                    except discord.NotFound:
                        logger.debug("Progress message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting progress message: {e}", exc_info=True)

                await gmgn_raid.unlock_channel(ctx.channel)
                channel_locked = True
                
            except Exception as e:
                logger.error(f"Error in raid_stop (GMGN): {e}", exc_info=True)

        # Add Dextools check
        if dextools_raid and ctx.channel.id in dextools_raid.locked_channels:
            try:
                challenge_data = dextools_raid.engagement_targets.get(ctx.channel.id)
                if challenge_data:
                    try:
                        lock_message = await ctx.channel.fetch_message(challenge_data['lock_message_id'])
                        if lock_message:
                            await lock_message.delete()
                    except discord.NotFound:
                        logger.debug("Lock message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting lock message: {e}", exc_info=True)
                        
                    try:
                        progress_message = await ctx.channel.fetch_message(challenge_data['message_id'])
                        if progress_message:
                            await progress_message.delete()
                    except discord.NotFound:
                        logger.debug("Progress message already deleted")
                    except Exception as e:
                        logger.error(f"Error deleting progress message: {e}", exc_info=True)

                await dextools_raid.unlock_channel(ctx.channel)
                channel_locked = True
                
            except Exception as e:
                logger.error(f"Error in raid_stop (Dextools): {e}", exc_info=True)

        if channel_locked:
            await ctx.send("Challenge ended manually. Channel unlocked!", delete_after=5)
        else:
            await ctx.send("No active challenge in this channel!", delete_after=5)

async def setup(bot):
    await bot.add_cog(ChannelManager(bot))