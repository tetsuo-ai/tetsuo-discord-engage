import discord
from discord.ext import commands
import os

class BaseRaid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.locked_channels = {}
        self.engagement_targets = {}
        self.raid_channel_id = int(os.getenv('RAID_CHANNEL_ID', 0)) or None

    async def check_raid_channel(self, ctx):
        """Check if the command is being used in the designated raid channel"""
        if not self.raid_channel_id:
            await ctx.send("❌ No raid channel has been set! An administrator must use !set_raid_channel first.", delete_after=10)
            return False
        
        if ctx.channel.id != self.raid_channel_id:
            await ctx.send("❌ This command can only be used in the designated raid channel.", delete_after=10)
            return False
            
        return True

    def create_progress_bar(self, current, target, length=20):
        """Create a visual progress bar"""
        percentage = min(current/target if target > 0 else 0, 1)
        filled = int(length * percentage)
        return f"[{'='*filled}{'-'*(length-filled)}]"

    async def lock_channel(self, channel):
        """Lock a channel from user messages"""
        overwrites = channel.overwrites_for(channel.guild.default_role)
        overwrites.send_messages = False
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrites)
        self.locked_channels[channel.id] = True

    async def unlock_channel(self, channel):
        """Unlock a channel for user messages"""
        overwrites = channel.overwrites_for(channel.guild.default_role)
        overwrites.send_messages = True
        await channel.set_permissions(channel.guild.default_role, overwrite=overwrites)
        self.locked_channels.pop(channel.id, None)
        self.engagement_targets.pop(channel.id, None)