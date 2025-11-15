# main.py - Sirul Member Control Bot (Fixed for Render Free Hobby - Flask + Simple Polling)
# Flask binds to port 10000 first (passes scan) + Bot polling in main

import os
import sqlite3
import logging
from datetime import date, datetime
from typing import List

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from flask import Flask

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set! Add to Render Environment Variables.")

DB_FILE = "inactivity.db"

# --- LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            user_id INTEGER,
            chat_id INTEGER,
            last_msg DATE NOT NULL,
            warned INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        )
    """)
    conn.commit()
    conn.close()

def record_message(user_id: int, chat_id: int):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO activity (user_id, chat_id, last_msg, warned)
        VALUES (?, ?, ?, 0)
        ON CONFLICT(user_id, chat_id) DO UPDATE SET
            last_msg = excluded.last_msg,
            warned = 0
    """, (user_id, chat_id, today))
    conn.commit()
    conn.close()

def get_all_in_chat(chat_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id, last_msg, warned FROM activity WHERE chat_id = ?", (chat_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def set_warned(user_id: int, chat_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE activity SET warned = 1 WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    conn.commit()
    conn.close()

def delete_user(user_id: int, chat_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM activity WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    conn.commit()
    conn.close()

# --- DAILY CHECK (00:05 UTC) ---
async def daily_check(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT chat_id FROM activity")
    chat_ids = [row[0] for row in cur.fetchall()]
    conn.close()

    today = date.today()

    for chat_id in chat_ids:
        if chat_id >= 0:  # Skip private chats
            continue

        rows = get_all_in_chat(chat_id)
        warn_list: List[str] = []
        kick_list: List[str] = []

        for user_id, last_msg_str, warned in rows:
            last_msg = date.fromisoformat(last_msg_str)
            days_ago = (today - last_msg).days

            # Day 4: Warning
            if days_ago == 4 and warned == 0:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="Warning: You haven't sent a message in 4 days.\n"
                             "Post something today or you will be removed tomorrow."
                    )
                    set_warned(user_id, chat_id)
                    member = await context.bot.get_chat_member(chat_id, user_id)
                    name = member.user.full_name or f"User {user_id}"
                    warn_list.append(name)
                except Exception as e:
                    log.warning(f"Warn failed {user_id}: {e}")

            # Day 5: Kick
            if days_ago >= 5:
                try:
                    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
                    delete_user(user_id, chat_id)
                    name = f"User {user_id}"
                    try:
                        member = await context.bot.get_chat_member(chat_id, user_id)
                        name = member.user.full_name
                    except:
                        pass
                    kick_list.append(name)
                except Exception as e:
                    log.warning(f"Kick failed {user_id}: {e}")

        # Post Lists
        if warn_list:
            await context.bot.send_message(
                chat_id=chat_id,
                text="**Warning: 4 Days Inactive**\n" + "\n".join(f"• {n}" for n in warn_list),
                parse_mode="Markdown"
            )
        if kick_list:
            await context.bot.send_message(
                chat_id=chat_id,
                text="**Removed: 5 Days Inactive**\n" + "\n".join(f"• {n}" for n in kick_list),
                parse_mode="Markdown"
            )

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "Sirul Member Control is **ACTIVE**!\n"
            "• Warns after **4 days** of no messages\n"
            "• Removes after **5 days**",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("Add me to a group and make me admin!")

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type not in ["group", "supergroup"] or user.is_bot:
        return
    record_message(user.id, chat.id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Error: %s", context.error)

# --- FLASK SERVER (Binds to PORT 10000 FIRST) ---
flask_app = Flask(__name__)

@flask_app.route('/', defaults={'path': ''})
@flask_app.route('/<path:path>')
def catch_all(path):
    return "Sirul Member Control Bot is LIVE!", 200

# --- MAIN ---
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & filters.ChatType.GROUPS & ~filters.COMMAND, any_message))
    app.add_error_handler(error_handler)

    # Daily job at 00:05 UTC
    app.job_queue.run_daily(
        callback=daily_check,
        time=datetime.strptime("00:05", "%H:%M").time(),
        name="daily_inactivity_check"
    )

    print("Bot is running! Add to any group as admin.")

    # Start bot polling
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        read_timeout=10,
        write_timeout=10,
        connect_timeout=10,
        pool_timeout=10
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    print(f"Starting Flask on port {port}...")
    flask_app.run(host='0.0.0.0', port=port, debug=False)
