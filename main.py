import os
import logging
import asyncio
from datetime import datetime, timedelta
from functools import wraps
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from twilio.rest import Client

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "YOUR_ADMIN_ID"))
TRIAL_USERS = set()
SUBSCRIBED_USERS = {}
USER_TWILIO_CREDS = {}  # Stores user_id: {'sid': '', 'token': '', 'account_name': '', 'balance': ''}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Subscription Plans
PLANS = {
    "free_1h": {"label": "🎉 1 Hour - Free 🌸", "duration": 1, "price": 0},
    "1d": {"label": "🔴 1 Day - 2$", "duration": 24, "price": 2},
    "7d": {"label": "🟠 7 Day - 10$", "duration": 24 * 7, "price": 10},
    "15d": {"label": "🟡 15 Day - 15$", "duration": 24 * 15, "price": 15},
    "30d": {"label": "🟢 30 Day - 20$", "duration": 24 * 30, "price": 20}
}

# Decorator to check subscription
def check_subscription(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        # Admin bypass
        if user_id == ADMIN_ID:
            return await func(update, context)
            
        # Check subscription
        if user_id in SUBSCRIBED_USERS and SUBSCRIBED_USERS[user_id] > datetime.utcnow():
            return await func(update, context)
        else:
            buttons = [[InlineKeyboardButton(plan["label"], callback_data=key)] for key, plan in PLANS.items()]
            markup = InlineKeyboardMarkup(buttons)
            await update.message.reply_text(
                "⚠️ আপনার Subscription একটিভ নেই! বট ব্যবহার করতে Subscription নিন:",
                reply_markup=markup
            )
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id in SUBSCRIBED_USERS and SUBSCRIBED_USERS[user_id] > datetime.utcnow():
        expiry_date = SUBSCRIBED_USERS[user_id]
        remaining = expiry_date - datetime.utcnow()
        days = remaining.days
        hours = remaining.seconds // 3600
        
        await update.message.reply_text(
            f"স্বাগতম {user.first_name}!\n\n"
            f"✅ আপনার Subscription একটিভ আছে!\n"
            f"⏳ মেয়াদ শেষ হবে: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"⏳ বাকি সময়: {days} দিন {hours} ঘন্টা\n\n"
            f"লগইন করতে /login কমান্ড ব্যবহার করুন"
        )
    else:
        buttons = [[InlineKeyboardButton(plan["label"], callback_data=key)] for key, plan in PLANS.items()]
        markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            "আপনার Subscriptions চালু নেই ♻️ চালু করার জন্য নিচের Subscription Choose করুন ✅",
            reply_markup=markup
        )

async def handle_plan_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id
    choice = query.data

    await query.message.delete()

    if choice == "free_1h":
        if user_id in TRIAL_USERS:
            await query.message.reply_text("⚠️ আপনি একবার ফ্রি ট্রায়াল নিয়েছেন। দয়া করে পেইড প্ল্যান ব্যবহার করুন।")
            return
        TRIAL_USERS.add(user_id)
        SUBSCRIBED_USERS[user_id] = datetime.utcnow() + timedelta(hours=1)
        await query.message.reply_text("✅ 1 ঘন্টার জন্য ফ্রি ট্রায়াল সক্রিয় করা হলো।")
        return

    plan = PLANS[choice]
    text = f"Please send ${plan['price']} to Binance Pay ID:\n"
    text += f"\nপেমেন্ট করে প্রমান হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490"
    text += f"\n\nYour payment details:\n"
    text += f"❄️ Name : {user.first_name}\n🆔 User ID: {user.id}\n👤 Username: @{user.username}\n📋 Plan: {plan['label']}\n💰 Amount: ${plan['price']}"

    await query.message.reply_text(text)

    notify_text = (
        f"{user.first_name} {plan['duration']} ঘন্টার Subscription নিতে চাচ্ছে।\n\n"
        f"🔆 User Name : {user.first_name}\n"
        f"🔆 User ID : {user_id}\n"
        f"🔆 Username : @{user.username}"
    )
    buttons = [
        [
            InlineKeyboardButton("Approve ✅", callback_data=f"approve|{user_id}|{choice}"),
            InlineKeyboardButton("Cancel ❌", callback_data=f"cancel|{user_id}")
        ]
    ]
    await context.bot.send_message(chat_id=ADMIN_ID, text=notify_text, reply_markup=InlineKeyboardMarkup(buttons))

async def handle_admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    action = data[0]
    user_id = int(data[1])

    if action == "approve":
        plan_key = data[2]
        plan = PLANS[plan_key]
        SUBSCRIBED_USERS[user_id] = datetime.utcnow() + timedelta(hours=plan["duration"])
        await context.bot.send_message(chat_id=user_id, text=f"✅ আপনার {plan['label']} Subscription চালু হয়েছে।")
        await query.edit_message_text(f"✅ {user_id} ইউজারের Subscription Approved.")

    elif action == "cancel":
        await context.bot.send_message(chat_id=user_id, text="❌ আপনার Subscription অনুরোধ বাতিল করা হয়েছে।")
        await query.edit_message_text(f"❌ {user_id} ইউজারের Subscription বাতিল করা হয়েছে।")

@check_subscription
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [[InlineKeyboardButton("Login 🔒", callback_data="login_prompt")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Login করতে নিচের বাটনে ক্লিক করুন",
        reply_markup=reply_markup
    )

async def handle_login_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    await query.message.reply_text(
        "আপনার Twilio Sid এবং Auth Token দিন ✅\nব্যবহার: <sid> <auth>"
    )

@check_subscription
async def handle_twilio_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    
    if len(text.split()) != 2:
        await update.message.reply_text("❌ ভুল ফরম্যাট! সঠিক ফরম্যাট: <sid> <auth>")
        return
    
    sid, auth = text.split()
    
    try:
        # Test Twilio credentials
        twilio_client = Client(sid, auth)
        account = twilio_client.api.accounts(sid).fetch()
        balance = float(twilio_client.balance.fetch().balance)
        
        # Store credentials
        USER_TWILIO_CREDS[user.id] = {
            'sid': sid,
            'token': auth,
            'account_name': account.friendly_name,
            'balance': balance
        }
        
        # Success message
        response = (
            f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n"
            f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account.friendly_name}\n"
            f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
            f"বিঃদ্রঃ নাম্বার কিনার আগে ব্যালেন্স চেক করে নিবেন ♻️\n"
            f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
        )
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Twilio login failed: {e}")
        await update.message.reply_text("Token Suspended 😃 অন্য টোকেন ব্যবহার করুন ✅")

@check_subscription
async def subscription_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id in SUBSCRIBED_USERS:
        expiry_date = SUBSCRIBED_USERS[user_id]
        remaining = expiry_date - datetime.utcnow()
        days = remaining.days
        hours = remaining.seconds // 3600
        
        await update.message.reply_text(
            f"✅ আপনার Subscription একটিভ আছে!\n"
            f"⏳ মেয়াদ শেষ হবে: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"⏳ বাকি সময়: {days} দিন {hours} ঘন্টা"
        )
    else:
        buttons = [[InlineKeyboardButton(plan["label"], callback_data=key)] for key, plan in PLANS.items()]
        markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            "⚠️ আপনার Subscription একটিভ নেই! বট ব্যবহার করতে Subscription নিন:",
            reply_markup=markup
        )

async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.utcnow()
    expired_users = []
    
    for user_id, expiry_date in list(SUBSCRIBED_USERS.items()):
        if expiry_date <= now:
            expired_users.append(user_id)
            del SUBSCRIBED_USERS[user_id]
            
    for user_id in expired_users:
        try:
            buttons = [[InlineKeyboardButton(plan["label"], callback_data=key)] for key, plan in PLANS.items()]
            markup = InlineKeyboardMarkup(buttons)
            await context.bot.send_message(
                chat_id=user_id,
                text="⚠️ আপনার Subscription এক্সপায়ার্ড হয়েছে! বট ব্যবহার চালিয়ে যেতে Renew করুন:",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Failed to notify expired user {user_id}: {e}")

async def subscription_checker(context: ContextTypes.DEFAULT_TYPE):
    while True:
        await check_expired_subscriptions(context)
        await asyncio.sleep(3600)  # Check every hour

async def webhook(request):
    data = await request.json()
    await application.update_queue.put(Update.de_json(data, application.bot))
    return web.Response(text="ok")

async def main():
    global application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("status", subscription_status))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(handle_plan_choice, pattern="^(free_1h|1d|7d|15d|30d)$"))
    application.add_handler(CallbackQueryHandler(handle_admin_decision, pattern="^(approve|cancel)\\|"))
    application.add_handler(CallbackQueryHandler(handle_login_prompt, pattern="^login_prompt$"))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_twilio_credentials))
    
    # Webhook setup
    app = web.Application()
    app.router.add_post("/", webhook)

    async with application:
        await application.start()
        await application.updater.start_polling()
        
        # Start subscription checker task
        asyncio.create_task(subscription_checker(application))
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
        await site.start()
        logger.info("Bot is up and running...")
        await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
