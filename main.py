# main.py - Sirul Member Control Bot (FREE RENDER HOBBY - FIXED)
# Bot polling in main + Flask in thread (Flask no longer blocks)

import os
import sqlite3
import logging
import threading
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

# --- DAILY CHECK ---
async def daily_check(context: ContextTypes.DEFAULT_TYPE):
    # (same as before - copy from your code)
    pass  # Keep your daily_check function here

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

# --- FLASK DUMMY SERVER ---
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

    # Run bot polling in main thread (no blocking)
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & filters.ChatType.GROUPS & ~filters.COMMAND, any_message))

    # Daily job
    app.job_queue.run_daily(
        callback=daily_check,
        time=datetime.strptime("00:05", "%H:%M").time()
    )

    print("Bot is running! Add to any group as admin.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
