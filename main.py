# main.py - Sirul Member Control Bot (FREE RENDER - NEVER STOPS)
import os
import sqlite3
import logging
import threading
import time
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

# --- DAILY CHECK (00:05 UTC) ---
async def daily_check(context: ContextTypes.DEFAULT_TYPE):
    # Your full daily_check function here (copy from previous)
    pass  # Keep your full function

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

# --- FLASK SERVER ---
flask_app = Flask(__name__)

@flask_app.route('/', defaults={'path': ''})
@flask_app.route('/<path:path>')
def home(path):
    return "Bot is LIVE!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    print(f"Flask started on port {port}")
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)

# --- BOT POLLING ---
def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & filters.ChatType.GROUPS & ~filters.COMMAND, any_message))
    app.job_queue.run_daily(daily_check, time=datetime.strptime("00:05", "%H:%M").time())
    print("Bot polling started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

# --- MAIN ---
if __name__ == "__main__":
    init_db()

    # Start Flask in thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start bot in thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Keep main thread alive forever
    print("Sirul Member Control Bot is LIVE 24/7!")
    while True:
        time.sleep(60)
