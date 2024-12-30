from telegram.ext import ApplicationBuilder
from telegram import ChatPermissions
import logging

logger = logging.getLogger('tetsuo_bot.telegram_utils')

class TelegramMessenger:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.app = None
        self.current_message_id = None

    async def initialize(self):
        """Initialize Telegram bot"""
        if not self.app:
            try:
                self.app = ApplicationBuilder().token(self.bot_token).build()
                await self.app.initialize()
                await self.app.start()
                logger.info("Telegram bot ready")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {e}", exc_info=True)
                return False
        return True

    async def cleanup(self):
        """Cleanup Telegram bot"""
        if self.app:
            await self.app.stop()
            await self.app.shutdown()
            self.app = None
            logger.info("Telegram bot stopped")

    async def lock_chat(self):
        """Lock the chat"""
        try:
            if not self.app:
                await self.initialize()
            await self.app.bot.set_chat_permissions(
                chat_id=self.chat_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            logger.info("Telegram chat locked")
        except Exception as e:
            logger.error(f"Failed to lock Telegram chat: {e}")

    async def unlock_chat(self):
        """Unlock the chat"""
        try:
            if not self.app:
                await self.initialize()
            await self.app.bot.set_chat_permissions(
                chat_id=self.chat_id,
                permissions=ChatPermissions(can_send_messages=True)
            )
            logger.info("Telegram chat unlocked")
        except Exception as e:
            logger.error(f"Failed to unlock Telegram chat: {e}")

    async def delete_message(self, message_id: int):
        """Delete a message by its ID"""
        try:
            if not self.app:
                await self.initialize()
            await self.app.bot.delete_message(chat_id=self.chat_id, message_id=message_id)
            logger.info(f"Telegram message {message_id} deleted")
        except Exception as e:
            logger.error(f"Error deleting Telegram message {message_id}: {e}", exc_info=True)

    def create_progress_message(self, metrics: dict, targets: dict) -> str:
        """Create formatted progress message"""
        filled = "🟩"
        empty = "⬜"
        bar_length = 10

        all_targets_met = all(metrics.get(metric, 0) >= target for metric, target in targets.items())
        header = "🎉 RAID COMPLETE! 🎉" if all_targets_met else "🎯 RAID IS ACTIVE UNTIL ALL TARGETS MET! 🎯"
        
        progress_bars = []
        for metric, target in targets.items():
            current = metrics.get(metric, 0)
            filled_blocks = min(int((current/target) * bar_length), bar_length) if target > 0 else 0
            bar = filled * filled_blocks + empty * (bar_length - filled_blocks)
            percentage = (current/target * 100) if target > 0 else 0
            status = "✅" if current >= target else ""
            progress_bars.append(f"{metric}: {current}/{target} ({percentage:.1f}%) {status}\n{bar}\n")

        return f"{header}\n\n" + "\n".join(progress_bars)
    
    async def send_raid_message(self, tweet_url: str, targets: dict, metrics: dict = None):
        """Send initial raid message with GIF"""
        try:
            if not self.app:
                await self.initialize()

            # Create progress message
            progress_text = self.create_progress_message(metrics or {}, targets)
            message = f"{progress_text}\n\n{tweet_url}"

            try:
                # Send with raid GIF
                sent = await self.app.bot.send_animation(
                    chat_id=self.chat_id,
                    animation="https://media.tenor.com/kEtaKa93XxIAAAPo/malks.mp4",
                    caption=message
                )
                
                # Detailed logging of message ID
                logger.info(f"Telegram raid message sent. Message ID: {sent.message_id}")
                self.current_message_id = sent.message_id
                
                # Additional logging of current state
                logger.debug(f"Current message ID after sending: {self.current_message_id}")
                
                return sent
            
            except Exception as e:
                logger.error(f"Error sending animation message: {e}", exc_info=True)
                raise
        
        except Exception as e:
            logger.error(f"Failed to send Telegram raid message: {e}", exc_info=True)
            raise

    async def update_progress(self, current_metrics: dict, targets: dict, tweet_url: str):
        # Log the current message ID at the start of the method
        logger.debug(f"Attempting to update Telegram progress. Current Message ID: {self.current_message_id}")
        
        if not self.current_message_id:
            logger.warning("No current message ID available for Telegram progress update")
            return

        try:
            progress_text = self.create_progress_message(current_metrics, targets)
            message = f"{progress_text}\n\n{tweet_url}"

            try:
                await self.app.bot.edit_message_caption(
                    chat_id=self.chat_id,
                    message_id=self.current_message_id,
                    caption=message
                )
                
                # Log successful update
                logger.info(f"Successfully updated Telegram message. Message ID: {self.current_message_id}")
            
            except Exception as e:
                if "message is not modified" in str(e).lower():
                    # This is normal - message hasn't changed
                    logger.debug("Telegram message unchanged - skipping update")
                    return
                elif "message not found" in str(e).lower():
                    # Log if message seems to have disappeared
                    logger.warning(f"Message with ID {self.current_message_id} not found. Clearing current message ID.")
                    self.current_message_id = None
                else:
                    # Log any other unexpected errors
                    logger.error(f"Unexpected error updating Telegram message: {e}")
                
        except Exception as e:
            logger.error(f"Failed to update Telegram progress: {e}")