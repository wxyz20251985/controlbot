# main.py - Sirul Member Control Bot (FREE RENDER HOBBY - FIXED)
# Bot polling in main + Flask in thread (Flask no longer blocks)

import os
import sqlite3
import logging
import threading
from datetime import date, datetime, timedelta
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
    raise ValueError("BOT_TOKEN not set!")

DB_FILE = "inactivity.db"

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

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
                        text="Warning: You haven't submitted selewat report in 4 days.\n"
                             "Submit today or you will be removed tomorrow."
                    )
                    set_warned(user_id, chat_id)
                    member = await context.bot.get_chat_member(chat_id, user_id)
                    name = member.user.full_name or f"User {user_id}"
                    warn_list.append(name)
                except Exception as e:
                    logging.warning(f"Warn failed {user_id}: {e}")

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
                    logging.warning(f"Kick failed {user_id}: {e}")

        # Post Lists in group
        if warn_list:
            await context.bot.send_message(
                chat_id=chat_id,
                text="**Warning: 4 Days No Selewat Report**\n" + "\n".join(f"• {n}" for n in warn_list),
                parse_mode="Markdown"
            )
        if kick_list:
            await context.bot.send_message(
                chat_id=chat_id,
                text="**Removed: 5 Days No Selewat Report**\n" + "\n".join(f"• {n}" for n in kick_list),
                parse_mode="Markdown"
            )

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "Sirul Wujud Member Control is **ACTIVE**!\n"
            "• Warns after **4 days** of no selewat reports\n"
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

# --- FLASK DUMMY SERVER (Port 10000) ---
flask_app = Flask(__name__)

@flask_app.route('/', defaults={'path': ''})
@flask_app.route('/<path:path>')
def home(path):
    return "Sirul Member Control Bot is LIVE!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    print(f"Flask server started on port {port}")
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)

# --- MAIN ---
if __name__ == "__main__":
    init_db()

    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Run bot polling in main thread
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & filters.ChatType.GROUPS & ~filters.COMMAND, any_message))

    # Daily job at 00:05 UTC
    app.job_queue.run_daily(
        callback=daily_check,
        time=datetime.strptime("00:05", "%H:%M").time(),
        name="daily_selewat_check"
    )

    print("Bot is running! Add to any group as admin.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
