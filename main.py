import os
import logging
import asyncio
from datetime import datetime, timedelta
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "YOUR_ADMIN_ID"))
TRIAL_USERS = set()
SUBSCRIBED_USERS = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Subscription Plans
PLANS = {
    "free_1h": {"label": "⬜ 1 Hour - Free 🌸", "duration": 1, "price": 0},
    "1d": {"label": "🔴 1 Day - 2$", "duration": 24, "price": 2},
    "7d": {"label": "🟠 7 Day - 10$", "duration": 24 * 7, "price": 10},
    "15d": {"label": "🟡 15 Day - 15$", "duration": 24 * 15, "price": 15},
    "30d": {"label": "🟢 30 Day - 20$", "duration": 24 * 30, "price": 20}
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id in SUBSCRIBED_USERS and SUBSCRIBED_USERS[user_id] > datetime.utcnow():
        await update.message.reply_text(
            f"স্বাগতম {user.first_name} আপনার Subscription চালু আছে\nলগইন করতে /login কমান্ড ব্যবহার করুন"
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
            InlineKeyboardButton("Appruve ✅", callback_data=f"approve|{user_id}|{choice}"),
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

async def webhook(request):
    data = await request.json()
    await application.update_queue.put(Update.de_json(data, application.bot))
    return web.Response(text="ok")

async def main():
    global application
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_plan_choice, pattern="^(free_1h|1d|7d|15d|30d)$"))
    application.add_handler(CallbackQueryHandler(handle_admin_decision, pattern="^(approve|cancel)\\|"))

    app = web.Application()
    app.router.add_post("/", webhook)

    async with application:
        await application.start()
        await application.updater.start_polling()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
        await site.start()
        logger.info("Bot is up and running...")
        await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
