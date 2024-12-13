import os
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
import logging

# Set up logging
logging.basicConfig(level=logging.WARN)
logger = logging.getLogger('discord')
logger.setLevel(logging.WARN)

# Load environment variables
load_dotenv()
token = os.getenv('DISCORD_TOKEN')

async def main():
    print("Starting bot initialization...")
    
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.presences = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        print(f'Successfully logged in as {bot.user.name} (ID: {bot.user.id})')
        print(f'Connected to {len(bot.guilds)} guilds')
        print('------')

    @bot.event
    async def on_connect():
        print("Bot connected to Discord!")

    @bot.event
    async def on_disconnect():
        print("Bot disconnected from Discord!")

    @bot.command()
    async def ping(ctx):
        await ctx.send('pong!')
    
    try:
        print("Loading engagement_bot extension...")
        await bot.load_extension('engagement_bot')
        print("Engagement bot loaded successfully!")
    except Exception as e:
        print(f"Failed to load engagement_bot: {e}")
    
    try:
        print("Attempting to start bot...")
        if not token:
            raise ValueError("No Discord token found in .env file")
        await bot.start(token)
    except Exception as e:
        print(f"Error starting bot: {e}")
        raise e

print("Script starting...")
asyncio.run(main())