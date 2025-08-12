# Telegram Auto-Reaction Bot with Forced Subscription (v20+ compatible)
# Professional version with robust error handling and structure.

from keep_alive import keep_alive
import logging
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ChatMemberHandler,
    CallbackQueryHandler,
)
from telegram.constants import ChatType
from telegram.error import BadRequest, TelegramError, Forbidden

# --- Configuration ---
# IMPORTANT: For production, it's highly recommended to use environment variables
# or a secure configuration management system instead of hardcoding tokens.
BOT_TOKEN = "8133117251:AAH2pr-gQ2bjr4EYxKhdk_tcPlqQxAaXF9Y"
MAIN_CHANNEL_USERNAME = "Unix_Bots"  # The @username of your mandatory channel.

# --- Reaction Emoji Lists ---
POSITIVE_REACTIONS = ["👍", "❤️", "🔥", "🎉", "👏", "🤩", "💯"]
FALLBACK_REACTIONS = ["👌", "😁", "🤔", "👀", "🤔"]

# --- Logging Setup ---
# Configure logging to provide detailed output for easier debugging.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Set a higher log level for the httpx library to avoid spamming the console.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- In-memory Storage ---
# A simple dictionary to store notifications for users who haven't started the bot.
# For a more scalable solution, consider using a database like SQLite or Redis.
pending_notifications = {}


# --- Helper Functions ---
async def is_user_member_of_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """
    Checks if a user is a member of the main channel.
    Returns True if the user is a member, False otherwise.
    """
    try:
        member = await context.bot.get_chat_member(
            chat_id=f"@{MAIN_CHANNEL_USERNAME}",
            user_id=user_id
        )
        # A user is considered a member if their status is creator, administrator, or member.
        return member.status in ["member", "administrator", "creator"]
    except BadRequest as e:
        # This can happen if the user ID is invalid or the chat is not found.
        logger.warning(f"BadRequest checking membership for user {user_id} in @{MAIN_CHANNEL_USERNAME}: {e}")
        return False
    except TelegramError as e:
        # Catch other potential Telegram API errors.
        logger.error(f"TelegramError checking membership for user {user_id}: {e}")
        return False


# --- Core Bot Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command in private chats and delivers pending notifications."""
    if not update.message or update.message.chat.type != ChatType.PRIVATE:
        return

    user = update.effective_user
    user_id = user.id
    
    # Deliver any pending notifications now that the user has started the bot.
    if user_id in pending_notifications:
        logger.info(f"Delivering {len(pending_notifications[user_id])} pending notification(s) to user {user_id}.")
        for notification in pending_notifications[user_id]:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=notification,
                    disable_web_page_preview=True
                )
            except (Forbidden, BadRequest) as e:
                logger.warning(f"Could not send pending notification to {user_id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error sending pending notification to {user_id}: {e}")
        # Clear notifications after attempting delivery.
        del pending_notifications[user_id]

    # Check membership and show the appropriate welcome message.
    if await is_user_member_of_channel(context, user_id):
        bot_username = (await context.bot.get_me()).username
        group_url = f"https://t.me/{bot_username}?startgroup=true"
        channel_url = f"https://t.me/{bot_username}?startchannel=true"
        
        keyboard = [
            [
                InlineKeyboardButton("➕ Add to Group ➕", url=group_url),
                InlineKeyboardButton("📢 Add to Channel 📢", url=channel_url)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🌟 **Welcome!**\n\nYou are a member of our main channel and can now use the bot.\n\n"
            "Add me to a group or channel using the buttons below:",
            reply_markup=reply_markup,
        )
    else:
        keyboard = [
            [InlineKeyboardButton(f"1. Join @{MAIN_CHANNEL_USERNAME}", url=f"https://t.me/{MAIN_CHANNEL_USERNAME}")],
            [InlineKeyboardButton("2. I Have Joined ✅", callback_data="check_join")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔒 **Access Required**\n\nTo use this bot, you must first join our main channel.\n\n"
            "Please join the channel and then click 'I Have Joined ✅'.",
            reply_markup=reply_markup,
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all inline button presses, primarily for checking channel join status."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_join":
        if await is_user_member_of_channel(context, user_id):
            bot_username = (await context.bot.get_me()).username
            group_url = f"https://t.me/{bot_username}?startgroup=true"
            channel_url = f"https://t.me/{bot_username}?startchannel=true"
            
            keyboard = [
                [
                    InlineKeyboardButton("➕ Add to Group ➕", url=group_url),
                    InlineKeyboardButton("📢 Add to Channel 📢", url=channel_url)
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="✅ **Thank you for joining!**\nYou can now add me to a group or channel:",
                reply_markup=reply_markup
            )
        else:
            await query.answer("❌ You haven't joined the channel yet. Please join and try again.", show_alert=True)


async def handle_chat_addition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    A unified handler for when the bot is added to a group or channel.
    It identifies who added the bot and sends them a private confirmation message.
    """
    if not update.my_chat_member:
        return

    chat_member = update.my_chat_member
    chat = chat_member.chat
    adder_user = chat_member.from_user
    new_status = chat_member.new_chat_member.status
    old_status = chat_member.old_chat_member.status

    # Determine if the bot was just added.
    was_added = new_status in ["member", "administrator"] and old_status not in ["member", "administrator"]
    if not was_added or not adder_user:
        return

    chat_title = chat.title or "this chat"
    private_msg = ""

    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        logger.info(f"Bot was added to group '{chat_title}' ({chat.id}) by {adder_user.id}.")
        private_msg = (
            f"✅ Thanks for adding me to the group **'{chat_title}'**!\n\n"
            "I'll automatically react to new messages there. My bro 😎"
        )
    elif chat.type == ChatType.CHANNEL and new_status == "administrator":
        logger.info(f"Bot was added to channel '{chat_title}' ({chat.id}) by {adder_user.id}.")
        private_msg = (
            f"📢 Thanks for adding me to the channel **'{chat_title}'**!\n\n"
            "I'll automatically react to new posts there. For best results, "
            "please ensure I have 'Add Reactions' permission."
        )

    if not private_msg:
        return

    # Try to send the confirmation message directly to the user who added the bot.
    try:
        await context.bot.send_message(chat_id=adder_user.id, text=private_msg)
        logger.info(f"Sent confirmation to user {adder_user.id} for chat '{chat_title}'.")
    except (Forbidden, BadRequest):
        logger.warning(f"Couldn't message user {adder_user.id} (hasn't started bot). Storing pending notification.")
        if adder_user.id not in pending_notifications:
            pending_notifications[adder_user.id] = []
        pending_notifications[adder_user.id].append(private_msg)
    except Exception as e:
        logger.error(f"Unexpected error sending confirmation to {adder_user.id}: {e}")


async def react_to_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reacts to a new post in a channel or group."""
    message = update.channel_post or update.message
    if not message or (message.text and message.text.startswith('/')) or message.via_bot:
        return

    # Skip status updates like new members joining.
    if message.new_chat_members or message.left_chat_member:
        return

    chat_id = message.chat_id
    message_id = message.message_id
    logger.info(f"New message {message_id} in chat {chat_id}. Attempting to react.")

    # Combine all reactions and try a few random ones to increase success rate.
    all_reactions = POSITIVE_REACTIONS + FALLBACK_REACTIONS
    
    for emoji in random.sample(all_reactions, min(len(all_reactions), 3)):
        try:
            await context.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[emoji],
                is_big=False
            )
            logger.info(f"Successfully reacted with '{emoji}' in chat {chat_id}.")
            return  # Exit after the first successful reaction.
        except TelegramError as e:
            logger.warning(f"Could not react with '{emoji}' in chat {chat_id}: {e}")
            await asyncio.sleep(0.3)  # Small delay before retrying.
        except Exception as e:
            logger.error(f"An unexpected error occurred while trying to react in {chat_id}: {e}")
            break # Stop trying if a non-Telegram error occurs.

    logger.error(f"Failed to react to message {message_id} in chat {chat_id} after all attempts.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    A global error handler to log all uncaught exceptions.
    This prevents the bot from crashing and provides valuable debug information.
    """
    logger.error("Exception while handling an update:", exc_info=context.error)


def main() -> None:
    """Sets up the bot, registers handlers, and starts polling for updates."""
    if not BOT_TOKEN or "YOUR_BOT_TOKEN" in BOT_TOKEN:
        logger.critical("!!! BOT TOKEN IS MISSING OR INVALID !!!")
        logger.critical("Please set your bot token in the configuration section.")
        return

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # --- Register Handlers ---
    # Global error handler (most important for stability).
    application.add_error_handler(error_handler)

    # Command to start the bot in a private chat.
    application.add_handler(CommandHandler("start", start_command, filters.ChatType.PRIVATE))
    
    # Handles the "I have joined" button press.
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^check_join$"))
    
    # Handles when the bot's status changes in a chat (added/removed/promoted).
    application.add_handler(ChatMemberHandler(handle_chat_addition, ChatMemberHandler.MY_CHAT_MEMBER))
    
    # Handles reacting to any message that isn't a command.
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, react_to_post))

    # --- Start the Bot ---
    logger.info("Starting bot...")
    # run_polling() is a blocking call that will keep the bot running.
    # It also handles graceful shutdowns on signals like Ctrl+C.
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    keep_alive()
    main()

