import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from datetime import datetime, timezone, timedelta

class ChannelManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.raid_channel_id = int(os.getenv('RAID_CHANNEL_ID', 0)) or None

    async def cleanup_messages(self):
        while True:
            try:
                if not self.raid_channel_id:
                    await asyncio.sleep(300)  # Sleep 5 mins if no raid channel set
                    continue
                    
                channel = self.bot.get_channel(self.raid_channel_id)
                if not channel:
                    await asyncio.sleep(300)
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
                            if message_age > (8 * 3600):  # 8 hours in seconds
                                await message.delete()
                                print(f"Deleted bot message")
                        # Non-bot messages: Delete if older than 15 minutes
                        else:
                            if message_age > (15 * 60):  # 15 minutes in seconds
                                await message.delete()
                                print(f"Deleted user message")
                                
                        # Add a small delay to avoid rate limits
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    print(f"Error cleaning messages in raid channel: {e}")
                    
                # Run cleanup every 5 minutes
                await asyncio.sleep(300)
                
            except Exception as e:
                print(f"Error in cleanup task: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying if there's an error

    @commands.Cog.listener()
    async def on_ready(self):
        print('ChannelManager is ready')
        self.cleanup_task = self.bot.loop.create_task(self.cleanup_messages())

    def cog_unload(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()

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
    async def set_raid_channel(self, ctx):
        """Set the current channel as the designated raid channel"""
        self.raid_channel_id = ctx.channel.id
        
        env_path = '.env'
        new_var = f'RAID_CHANNEL_ID={ctx.channel.id}'
        
        if os.path.exists(env_path):
            with open(env_path, 'r') as file:
                lines = file.readlines()
            
            found = False
            for i, line in enumerate(lines):
                if line.startswith('RAID_CHANNEL_ID='):
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
        
        await ctx.send(f"✅ This channel has been set as the raid channel. All raid commands will only work here.\nChannel ID: `{ctx.channel.id}`", delete_after=30)

    @commands.command(name='raid_stop')
    @commands.has_permissions(manage_channels=True)
    async def raid_stop(self, ctx):
        """End the current engagement challenge and unlock the channel"""
        if not await self.check_raid_channel(ctx):
            return

        # Get the active raids from both raid cogs
        twitter_raid = self.bot.get_cog('TwitterRaid')
        cmc_raid = self.bot.get_cog('CMCRaid')
        
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
                        print("Lock message already deleted")
                    except Exception as e:
                        print(f"Error deleting lock message: {e}")
                        
                    try:
                        # Delete progress message
                        progress_message = await ctx.channel.fetch_message(challenge_data['message_id'])
                        if progress_message:
                            await progress_message.delete()
                    except discord.NotFound:
                        print("Progress message already deleted")
                    except Exception as e:
                        print(f"Error deleting progress message: {e}")

                await twitter_raid.unlock_channel(ctx.channel)
                channel_locked = True
                
            except Exception as e:
                print(f"Error in raid_stop (Twitter): {e}")
                
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
                        print("Lock message already deleted")
                    except Exception as e:
                        print(f"Error deleting lock message: {e}")
                        
                    try:
                        # Delete progress message
                        progress_message = await ctx.channel.fetch_message(challenge_data['message_id'])
                        if progress_message:
                            await progress_message.delete()
                    except discord.NotFound:
                        print("Progress message already deleted")
                    except Exception as e:
                        print(f"Error deleting progress message: {e}")

                await cmc_raid.unlock_channel(ctx.channel)
                channel_locked = True
                
            except Exception as e:
                print(f"Error in raid_stop (CMC): {e}")

        if channel_locked:
            await ctx.send("Challenge ended manually. Channel unlocked!", delete_after=5)
        else:
            await ctx.send("No active challenge in this channel!", delete_after=5)

async def setup(bot):
    await bot.add_cog(ChannelManager(bot))