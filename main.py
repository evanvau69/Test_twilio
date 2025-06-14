import os
import logging
import asyncio
import datetime
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from twilio.rest import Client

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_sessions = {}  # user_id -> {sid, auth, client}
login_messages = {}  # user_id -> login msg id
subscriptions = {}  # user_id -> expiry datetime
free_trial_used = set()  # user_id set

plans = {
    "1h_free": {"label": "⬜ 1 Hour - Free 🌸", "duration": 1, "unit": "hours", "price": 0},
    "1d": {"label": "🔴 1 Day - 2$", "duration": 1, "unit": "days", "price": 2},
    "7d": {"label": "🟠 7 Day - 10$", "duration": 7, "unit": "days", "price": 10},
    "15d": {"label": "🟡 15 Day - 15$", "duration": 15, "unit": "days", "price": 15},
    "30d": {"label": "🟢 30 Day - 20$", "duration": 30, "unit": "days", "price": 20}
}

def has_active_subscription(user_id):
    expiry = subscriptions.get(user_id)
    return expiry and expiry > datetime.datetime.now()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if has_active_subscription(user.id):
        await update.message.reply_text(
            f"স্বাগতম {user.first_name} আপনার Subscription চালু আছে ✨\n"
            f"Login করতে /login কমান্ড ব্যবহার করুন ✅"
        )
    else:
        buttons = [
            [InlineKeyboardButton(p["label"], callback_data=f"sub_{key}")]
            for key, p in plans.items()
        ]
        await update.message.reply_text(
            "আপনার Subscriptions চালু নেই ♻️ চালু করার জন্য নিচের Subscription Choose করুন ✅",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def handle_subscription_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    choice = query.data.replace("sub_", "")
    plan = plans.get(choice)
    if not plan:
        return

    await context.bot.delete_message(chat_id=user.id, message_id=query.message.message_id)

    if choice == "1h_free":
        if user.id in free_trial_used:
            await query.message.reply_text("⚠️ আপনি ইতোমধ্যে ফ্রি ট্রায়াল গ্রহণ করেছেন। অন্য প্ল্যান বেছে নিন।")
        else:
            delta = datetime.timedelta(**{plan["unit"]: plan["duration"]})
            subscriptions[user.id] = datetime.datetime.now() + delta
            free_trial_used.add(user.id)
            await query.message.reply_text("✅ ফ্রি ট্রায়াল ১ ঘণ্টার জন্য চালু করা হয়েছে!")
    else:
        msg = (
            f"Please send ${plan['price']} to Binance Pay ID:
"
            f"পেমেন্ট করে প্রমাণ হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490\n\n"
            f"Your payment details:\n"
            f"❄️ Name : {user.first_name}\n"
            f"🆔 User ID: {user.id}\n"
            f"👤 Username: @{user.username if user.username else 'N/A'}\n"
            f"📋 Plan: {plan['label']}\n"
            f"💰 Amount: ${plan['price']}"
        )
        await query.message.reply_text(msg)

        admin_msg = (
            f"{user.first_name} {plan['duration']} {plan['unit']} সময়ের জন্য Subscription নিতে চাচ্ছে।\n\n"
            f"🔆 User Name : {user.first_name}\n"
            f"🔆 User ID : {user.id}\n"
            f"🔆 Username : @{user.username if user.username else 'N/A'}"
        )
        admin_buttons = [
            [
                InlineKeyboardButton("Appruve ✅", callback_data=f"approve_{user.id}_{choice}"),
                InlineKeyboardButton("Cancel ❌", callback_data=f"cancel_{user.id}")
            ]
        ]
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(admin_buttons))

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("approve_"):
        _, uid, plan_key = data.split("_")
        uid = int(uid)
        plan = plans.get(plan_key)
        if not plan:
            return
        delta = datetime.timedelta(**{plan["unit"]: plan["duration"]})
        subscriptions[uid] = datetime.datetime.now() + delta
        await context.bot.send_message(chat_id=uid, text=f"✅ আপনার {plan['label']} Subscription চালু করা হয়েছে!")
        await query.edit_message_text("✅ Approve করা হয়েছে")
    elif data.startswith("cancel_"):
        uid = int(data.split("_")[1])
        await context.bot.send_message(chat_id=uid, text="❌ আপনার Subscription বাতিল করা হয়েছে।")
        await query.edit_message_text("🚫 Cancel করা হয়েছে")

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_active_subscription(update.effective_user.id):
        await update.message.reply_text("⚠️ আগে Subscription চালু করুন। /start দিয়ে শুরু করুন।")
        return
    keyboard = [
        [InlineKeyboardButton("Login 🔒", callback_data="start_login")]
    ]
    msg = await update.message.reply_text(
        "Login করতে নিচের বাটনে ক্লিক করুন",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    login_messages[update.effective_user.id] = msg.message_id

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data.startswith("sub_"):
        await handle_subscription_choice(update, context)
    elif query.data.startswith("approve_") or query.data.startswith("cancel_"):
        await handle_admin_approval(update, context)
    elif query.data == "start_login":
        user_id = query.from_user.id
        chat_id = query.message.chat.id
        old_msg_id = login_messages.get(user_id)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text="আপনার Sid এবং Auth Token দিন ✅\nব্যবহার : <sid> <auth>"
        )
    await query.answer()

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not has_active_subscription(user_id):
        return
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) == 2:
        sid, auth = parts
        try:
            client = Client(sid, auth)
            account = client.api.accounts(sid).fetch()
            balance_info = client.api.v2010.balance.fetch()
            balance = float(balance_info.balance)
            user_sessions[user_id] = {"sid": sid, "auth": auth, "client": client}
            await update.message.reply_text(
                f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account.friendly_name}\n"
                f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
                f"বিঃদ্রঃ নাম্বার কিনার আগে ব্যালেন্স চেক করে নিবেন ♻️\n\n"
                f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
            )
        except Exception as e:
            await update.message.reply_text("Token Suspended 😃 অন্য টোকেন ব্যবহার করুন ✅")
            logger.warning(f"Login failed for user {user_id}: {e}")

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sid_auth))

    aio_app = web.Application()
    aio_app.add_routes([web.post("/", app.webhook_handler())])

    webhook_url = os.getenv("WEBHOOK_URL")
    await app.bot.set_webhook(webhook_url)

    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "8080")))
    await site.start()

    print("Bot is running via webhook...")
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
