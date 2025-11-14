# main.py - Sirul Member Control Bot (FREE 24/7 on Render)
import os
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "members.db"

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS members (
            user_id INTEGER,
            chat_id INTEGER,
            username TEXT,
            last_active TEXT,
            warned INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        )
    ''')
    conn.commit()
    conn.close()

# --- HELPERS ---
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

async def log_activity(user, chat_id):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''
        INSERT INTO members (user_id, chat_id, username, last_active, warned)
        VALUES (?, ?, ?, ?, 0)
        ON CONFLICT(user_id, chat_id) DO UPDATE SET
            last_active = excluded.last_active,
            username = excluded.username,
            warned = 0
    ''', (user.id, chat_id, user.username or user.first_name, now))
    conn.commit()
    conn.close()

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ['group', 'supergroup']:
        await update.message.reply_text(
            "Sirul Member Control is **ACTIVE**!\n"
            "• Warns after **4 days** of no messages\n"
            "• Removes after **5 days**",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("Add me to a group as admin!")

async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ['group', 'supergroup']:
        user = update.effective_user
        await log_activity(user, update.effective_chat.id)

# --- DAILY CHECK ---
async def daily_inactivity_check(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now()
    four_days_ago = (now - timedelta(days=4)).date().isoformat()
    five_days_ago = (now - timedelta(days=5)).date().isoformat()

    # Warn after 4 days
    c.execute('''
        SELECT user_id, chat_id, username FROM members
        WHERE DATE(last_active) <= ? AND warned = 0
    ''', (four_days_ago,))
    to_warn = c.fetchall()

    for row in to_warn:
        user_id, chat_id, username = row
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Warning: You haven't sent a message in 4 days.\n"
                     f"Post something today or you will be removed."
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"**Warning: 4 Days Inactive**\n• @{username or user_id}",
                parse_mode='Markdown'
            )
            c.execute('UPDATE members SET warned = 1 WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
        except:
            pass

    # Kick after 5 days
    c.execute('''
        SELECT user_id, chat_id, username FROM members
        WHERE DATE(last_active) <= ?
    ''', (five_days_ago,))
    to_kick = c.fetchall()

    kicked_list = []
    for row in to_kick:
        user_id, chat_id, username = row
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            kicked_list.append(f"• @{username or user_id}")
            c.execute('DELETE FROM members WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
        except:
            pass

    if kicked_list:
        await context.bot.send_message(
            chat_id=chat_id,
            text="**Removed: 5 Days Inactive**\n" + "\n".join(kicked_list),
            parse_mode='Markdown'
        )

    conn.commit()
    conn.close()

# --- MAIN ---
async def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message))

    # Daily job at 00:05
    job_queue = app.job_queue
    job_queue.run_daily(
        daily_inactivity_check,
        time=datetime.strptime("00:05", "%H:%M").time()
    )

    print("Bot is running! Add to any group as admin.")

    # For Render Web Service (FREE) — bind to port
    port = int(os.environ.get("PORT", 10000))
    await app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        # Remove host/port for Background Worker
        # host='0.0.0.0', port=port  # Uncomment only for Web Service
    )

if __name__ == "__main__":
    asyncio.run(main())
