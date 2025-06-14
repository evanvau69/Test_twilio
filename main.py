import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from twilio.rest import Client
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage
user_subscriptions = {}
free_trial_used = set()
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    full_name = update.effective_user.full_name

    # Check if subscription exists and is still active
    now = datetime.now()
    if user_id in user_subscriptions and user_subscriptions[user_id] > now:
        await update.message.reply_text(
            f"স্বাগতম {full_name} ✨\n\nআপনার Subscription চালু আছে ✅\nটোকেন দিয়ে লগইন করতে /login ব্যবহার করুন 🔐"
        )
    else:
        buttons = [
            [InlineKeyboardButton("🎉 1 Hour - Free 🌸", callback_data="sub_free")],
            [InlineKeyboardButton("🔴 1 Day - 2$", callback_data="sub_1")],
            [InlineKeyboardButton("🟠 7 Day - 10$", callback_data="sub_7")],
            [InlineKeyboardButton("🟡 15 Day - 15$", callback_data="sub_15")],
            [InlineKeyboardButton("🟢 30 Day - 20$", callback_data="sub_30")],
        ]
        await update.message.reply_text(
            "আপনার Subscriptions চালু নেই ♻️\nচালু করার জন্য নিচের Subscription Choose করুন ✅",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def handle_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id
    full_name = user.full_name
    username = user.username or "NoUsername"
    now = datetime.now()

    if query.data == "sub_free":
        if user_id in free_trial_used:
            await query.edit_message_text("আপনি একবার ফ্রি ট্রায়াল নিয়েছেন ✅")
        else:
            free_trial_used.add(user_id)
            user_subscriptions[user_id] = now + timedelta(hours=1)
            await query.edit_message_text("✅ 1 ঘন্টার ফ্রি সাবস্ক্রিপশন চালু হয়েছে!")
    else:
        plans = {
            "sub_1": (1, 2),
            "sub_7": (7, 10),
            "sub_15": (15, 15),
            "sub_30": (30, 20)
        }
        days, amount = plans[query.data]
        msg = f"Please send ${amount} to Binance Pay ID:\n\n"
        msg += "পেমেন্ট করে প্রমাণ হিসাবে Admin এর কাছে স্ক্রিনশট অথবা Transaction ID দিন 👉 @Mr_Evan3490\n\n"
        msg += f"Your payment details:\n❄️ Name: {full_name}\n🆔 User ID: `{user_id}`\n👤 Username: @{username}\n📋 Plan: {days} Day\n💰 Amount: ${amount}"
        await query.edit_message_text(msg, parse_mode="Markdown")

        # Notify admin
        admin_msg = (
            f"{full_name} {days} দিনের Subscription নিতে চাচ্ছে।\n\n"
            f"🔆 User Name: {full_name}\n🔆 User ID: `{user_id}`\n🔆 Username: @{username}"
        )
        buttons = [
            [
                InlineKeyboardButton("Approve ✅", callback_data=f"approve_{user_id}_{days}"),
                InlineKeyboardButton("Cancel ❌", callback_data=f"cancel_{user_id}")
            ]
        ]
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def admin_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("approve_"):
        _, uid, days = data.split("_")
        user_id = int(uid)
        days = int(days)
        user_subscriptions[user_id] = datetime.now() + timedelta(days=days)
        await query.edit_message_text("✅ Subscription Approved")
        await context.bot.send_message(chat_id=user_id, text=f"✅ আপনার {days} দিনের Subscription চালু হয়েছে!")
    elif data.startswith("cancel_"):
        _, uid = data.split("_")
        user_id = int(uid)
        await query.edit_message_text("❌ Subscription Cancelled")
        await context.bot.send_message(chat_id=user_id, text=f"❌ আপনার Subscription অনুরোধ বাতিল করা হয়েছে।")

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton("Login 🔒", callback_data="twilio_login")]]
    await update.message.reply_text("Login করতে নিচের বাটনে ক্লিক করুন", reply_markup=InlineKeyboardMarkup(buttons))

async def twilio_login_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    await context.bot.send_message(chat_id=query.from_user.id, text="আপনার Sid এবং Auth Token দিন ✅\nব্যবহার : `<sid> <auth>`", parse_mode="Markdown")

async def handle_sid_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_subscriptions or user_subscriptions[user_id] < datetime.now():
        return

    msg = update.message.text.strip()
    if len(msg.split()) != 2:
        return
    sid, auth = msg.split()
    try:
        client = Client(sid, auth)
        acc = client.api.accounts(sid).fetch()
        balance = client.api.v2010.balance.fetch()
        usd_balance = round(float(balance.balance), 2)
        user_sessions[user_id] = {"sid": sid, "auth": auth}
        await update.message.reply_text(
            f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥 🎉\n\n"
            f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {acc.friendly_name}\n"
            f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${usd_balance}\n\n"
            f"বিঃদ্রঃ নাম্বার কিনার আগে ব্যালেন্স চেক করে নিবেন ♻️\n\nFounded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
        )
    except Exception as e:
        await update.message.reply_text("Token Suspended 😃 অন্য টোকেন ব্যবহার করুন ✅")

async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_subscription, pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(admin_response, pattern="^(approve_|cancel_)"))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CallbackQueryHandler(twilio_login_button, pattern="^twilio_login$"))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_sid_auth))

    async def webhook(request):
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response()

    app_runner = web.AppRunner(web.Application())
    await app_runner.setup()
    site = web.TCPSite(app_runner, "0.0.0.0", 80)
    await site.start()
    await app.initialize()
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
