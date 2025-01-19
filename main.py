import os
import asyncio
import signal
from dotenv import load_dotenv
import discord
from discord.ext import commands
import logging
from logging.handlers import RotatingFileHandler

# Set up logging
os.makedirs('logs', exist_ok=True)
detailed_formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s'
)
simple_formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s: %(message)s'
)

# File handler
file_handler = RotatingFileHandler(
    'logs/discord_bot.log',
    maxBytes=10485760,  # 10MB
    backupCount=5
)
file_handler.setFormatter(detailed_formatter)
file_handler.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(simple_formatter)
console_handler.setLevel(logging.INFO)

# Root logger setup
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Discord logger specific setup
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.INFO)

# Main application logger
logger = logging.getLogger('tetsuo_bot')

# Load environment variables
load_dotenv()
token = os.getenv('DISCORD_TOKEN')

async def shutdown(signal, bot):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info(f"Received exit signal {signal.name}...")
    
    # Close the Discord bot connection first
    try:
        logger.info("Closing Discord connection...")
        await bot.close()
    except Exception as e:
        logger.error(f"Error closing Discord connection: {e}")

    # Then cancel any remaining tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        logger.info(f"Cancelling {len(tasks)} outstanding tasks")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        
    logger.info("Shutdown complete.")

async def main():
    logger.info("Starting bot initialization...")
    
    # Set up signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, bot)))
    
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.presences = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        logger.info(f'Successfully logged in as {bot.user.name} (ID: {bot.user.id})')
        logger.info(f'Connected to {len(bot.guilds)} guilds')
        logger.info('------')

    @bot.event
    async def on_connect():
        logger.info("Bot connected to Discord!")

    @bot.event
    async def on_disconnect():
        logger.warning("Bot disconnected from Discord!")

    @bot.command()
    async def ping(ctx):
        await ctx.send('pong!')
    
    try:
        # Load channel manager first
        logger.info("Loading Channel manager extension...")
        await bot.load_extension('cogs.channel_manager')
        logger.info("Channel manager loaded successfully!")

        # Load raid extensions
        logger.info("Loading Twitter raid extension...")
        await bot.load_extension('cogs.twitter_raid')
        logger.info("Twitter raid loaded successfully!")
        
        logger.info("Loading CMC raid extension...")
        await bot.load_extension('cogs.cmc_raid')
        logger.info("CMC raid loaded successfully!")

        logger.info("Loading Gecko raid extension...")
        await bot.load_extension('cogs.gecko_raid')
        logger.info("Gecko raid loaded successfully!")

        logger.info("Loading Dextools raid extension...")
        await bot.load_extension('cogs.dextools_raid')
        logger.info("Dextools raid loaded successfully!")

        logger.info("Loading Whale Watcher extension...")
        await bot.load_extension('cogs.whale_watcher')
        logger.info("Whale Watcher loaded successfully!")
        
    except Exception as e:
        logger.error(f"Failed to load extension: {e}", exc_info=True)
    
    try:
        logger.info("Attempting to start bot...")
        if not token:
            logger.critical("No Discord token found in .env file")
            raise ValueError("No Discord token found in .env file")
        await bot.start(token)
    except Exception as e:
        logger.exception(f"Error starting bot: {e}")
        raise e

if __name__ == "__main__":
    try:
        logger.info("Script starting...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        logger.info("Bot shutdown complete.")