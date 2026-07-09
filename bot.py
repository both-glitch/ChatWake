import telebot
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from database import (
    create_tables,
    save_group,
    save_teammate,
    delete_group,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TOKEN = os.getenv("TOKEN")
bot = telebot.TeleBot(TOKEN)


# ---------- AUTO-DETECT NEW OR REMOVED GROUPS ----------
@bot.my_chat_member_handler()
def handle_bot_membership_change(update):
    chat = update.chat
    new_status = update.new_chat_member.status
    added_by = update.from_user.id

    if new_status in ("member", "administrator"):
        save_group(chat.id, chat.title or "Untitled Group", owner_id=added_by)
        print(f"Bot added to '{chat.title}' ({chat.id}) by user {added_by}")

    elif new_status in ("left", "kicked"):
        delete_group(chat.id)
        print(f"Bot removed from group: {chat.title} ({chat.id}). Cleaned from database.")


# ---------- CAPTURE MESSAGES PER GROUP ----------
@bot.message_handler(func=lambda message: message.chat.type in ("group", "supergroup"))
def handle_message(message):
    user = message.from_user
    chat_id = message.chat.id

    save_group(chat_id, message.chat.title or "Untitled Group")

    first_name = user.first_name or ""
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    username = user.username if user.username else full_name

    last_seen_utc = datetime.fromtimestamp(message.date, tz=timezone.utc).replace(tzinfo=None)
    last_seen = last_seen_utc.strftime("%Y-%m-%d %H:%M:%S")

    save_teammate(user.id, chat_id, full_name, username, last_seen)
    print(f"[{chat_id}] Captured: {full_name} (@{username}) at {last_seen} UTC")


# ---------- ACTIONS TRIGGERED FROM THE UI ----------

def send_wake_up(chat_id, username):
    bot.send_message(chat_id, f"⏰ WAKE UP @{username}! You have been inactive!")
    print(f"Wake up sent to @{username} in {chat_id}")


def send_anonymous_nudge(chat_id, username):
    bot.send_message(
        chat_id,
        f"👀 Someone in the group noticed @{username} has been quiet for a while..."
    )
    print(f"Anonymous nudge sent to @{username} in {chat_id}")


# NOTE: no bot.polling() and no background thread here anymore.
# app.py drives everything via webhooks + a scheduled status refresh.