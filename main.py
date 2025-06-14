import os
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          CallbackQueryHandler, MessageHandler, filters)
import aiohttp

BOT_TOKEN = "আপনার_টেলিগ্রাম_বট_টোকেন"
ADMIN_ID = 123456789  # আপনার টেলিগ্রাম ID এখানে বসান
BINANCE_PAY_ID = "your-binance-pay-id"  # এখানেও ID বসান

# Simple in-memory DB
subscriptions = {}
free_trial_used = set()
temp_login_prompt = {}
sessions = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Plans
PLANS = {
    "free": {"label": "⬜ 1 Hour - Free 🌸", "duration": 1, "price": 0},
    "1d": {"label": "🔴 1 Day - 2$", "duration": 24, "price": 2},
    "7d": {"label": "🟠 7 Day - 10$", "duration": 24*7, "price": 10},
    "15d": {"label": "🟡 15 Day - 15$", "duration": 24*15, "price": 15},
    "30d": {"label": "🟢 30 Day - 20$", "duration": 24*30, "price": 20},
}

# Check subscription
def is_active(user_id):
    exp = subscriptions.get(user_id)
    return exp and datetime.utcnow() < exp

# Start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_active(user.id):
        await update.message.reply_text(
            f"স্বাগতম {user.first_name} ✨\nআপনার Subscription চালু আছে ♻️\n\nটোকেন দিয়ে Login করুন 🔐\nLogin করতে /login ব্যবহার করুন ✅"
        )
    else:
        btns = [
            [InlineKeyboardButton(p['label'], callback_data=key)]
            for key, p in PLANS.items()
        ]
        markup = InlineKeyboardMarkup(btns)
        await update.message.reply_text(
            "আপনার Subscriptions চালু নেই ♻️\nচালু করার জন্য নিচের Subscription Choose করুন ✅",
            reply_markup=markup
        )

# Handle plan selection
async def plan_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    plan_key = query.data
    await query.answer()
    plan = PLANS[plan_key]

    await query.message.delete()

    if plan_key == "free":
        if user.id in free_trial_used:
            await query.message.reply_text("❌ আপনি একবার Free Trial ব্যবহার করেছেন।")
        else:
            subscriptions[user.id] = datetime.utcnow() + timedelta(hours=1)
            free_trial_used.add(user.id)
            await query.message.reply_text("✅ আপনার Free Trial একটিভ হয়েছে ১ ঘন্টার জন্য।")
    else:
        message = (
            f"Please send ${plan['price']} to Binance Pay ID: {BINANCE_PAY_ID}\n\n"
            "পেমেন্ট করে স্কিনশর্ট বা Transaction ID দিন Admin কে: @Mr_Evan3490\n\n"
            f"Your payment details:\n"
            f"❄️ Name : {user.first_name}\n"
            f"🆔 User ID: {user.id}\n"
            f"👤 Username: @{user.username or 'N/A'}\n"
            f"📋 Plan: {plan['label']}\n"
            f"💰 Amount: ${plan['price']}"
        )
        await query.message.reply_text(message)

        admin_msg = (
            f"{user.first_name} {plan['duration']} ঘণ্টার Subscription নিতে চাচ্ছে।\n\n"
            f"🔆 User Name : {user.first_name}\n"
            f"🔆 User ID : {user.id}\n"
            f"🔆 Username : @{user.username or 'N/A'}"
        )
        btns = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Approve ✅", callback_data=f"approve_{user.id}_{plan['duration']}"),
                InlineKeyboardButton("Cancel ❌", callback_data=f"cancel_{user.id}")
            ]
        ])
        await context.bot.send_message(ADMIN_ID, admin_msg, reply_markup=btns)

# Approve/Cancel
async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_")
    action, uid = data[0], int(data[1])

    if action == "approve":
        duration = int(data[2])
        subscriptions[uid] = datetime.utcnow() + timedelta(hours=duration)
        await context.bot.send_message(uid, f"✅ আপনার Subscription {duration} ঘণ্টার জন্য চালু হয়েছে।")
    else:
        await context.bot.send_message(uid, "❌ আপনার Subscription বাতিল করা হয়েছে।")
    await query.message.delete()

# /login
async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("Login 🔒", callback_data="do_login")]
    ])
    await update.message.reply_text("Login করতে নিচের বাটনে ক্লিক করুন", reply_markup=btn)

async def prompt_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    temp_login_prompt[query.from_user.id] = True
    await query.message.reply_text("আপনার Sid এবং Auth Token দিন ✅\nব্যবহার : <sid> <auth>")

async def handle_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in temp_login_prompt:
        return
    parts = update.message.text.strip().split()
    if len(parts) != 2:
        await update.message.reply_text("ফরম্যাট ভুল ❌\nব্যবহার : <sid> <auth>")
        return

    sid, token = parts
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json"
    auth = aiohttp.BasicAuth(sid, token)

    async with aiohttp.ClientSession(auth=auth) as session:
        async with session.get(url) as res:
            if res.status == 200:
                data = await res.json()
                name = data.get("friendly_name", "N/A")
                balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
                async with session.get(balance_url) as b_res:
                    if b_res.status == 200:
                        balance_data = await b_res.json()
                        balance = balance_data.get("balance", "0.00")
                    else:
                        balance = "Unknown"

                sessions[user.id] = {"sid": sid, "token": token}
                await update.message.reply_text(
                    f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                    f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {name}\n"
                    f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance}\n\n"
                    "বিঃদ্রঃ নাম্বার কিনার আগে ব্যালেন্স চেক করে নিবেন ♻️\n\nFounded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
                )
            else:
                await update.message.reply_text("Token Suspended 😃 অন্য টোকেন ব্যবহার করুন ✅")
    del temp_login_prompt[user.id]

# MAIN
async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CallbackQueryHandler(plan_select, pattern="^(free|1d|7d|15d|30d)$"))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^(approve|cancel)_"))
    app.add_handler(CallbackQueryHandler(prompt_token, pattern="^do_login$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token))

    await app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url="https://your-render-url.onrender.com"
    )

if __name__ == "__main__":
    asyncio.run(main())
