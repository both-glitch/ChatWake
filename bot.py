import telebot
import os
import random
WAKE_UP_MESSAGES = [
    "WAKE UP @{u}! You have been inactive.",
    "@{u}, the group hasn't heard from you in a while. Time to check in!",
    "Paging @{u}... anyone home?",
    "@{u} has officially entered ghost mode. Someone send help.",
    "Hey @{u}, your team is waiting on you!",
]

NUDGE_MESSAGES = [
    "Someone in the group noticed @{u} has been quiet for a while.",
    "Psst... has anyone seen @{u} lately?",
    "@{u} might need a gentle reminder to check the chat.",
    "It's been a bit quiet from @{u}'s side. Just a nudge!",
    "A friendly reminder to @{u}: the group is still here.",
]

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
    """Publicly mention someone in their group to wake them up."""
    try:
        message = random.choice(WAKE_UP_MESSAGES).format(u=username)
        bot.send_message(chat_id, message)
        print(f"Wake up sent to @{username} in {chat_id}")
        return True
    except Exception as e:
        print(f"FAILED to send wake up to @{username} in {chat_id}: {e}")
        return False


def send_anonymous_nudge(chat_id, username):
    """Send a nudge that doesn't reveal who triggered it."""
    try:
        message = random.choice(NUDGE_MESSAGES).format(u=username)
        bot.send_message(chat_id, message)
        print(f"Anonymous nudge sent to @{username} in {chat_id}")
        return True
    except Exception as e:
        print(f"FAILED to send nudge to @{username} in {chat_id}: {e}")
        return False


# NOTE: no bot.polling() and no background thread here anymore.
# app.py drives everything via webhooks + a scheduled status refresh.