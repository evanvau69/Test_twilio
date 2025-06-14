import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import random
import re
from datetime import datetime, timedelta

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
RENDER_URL = os.getenv("RENDER_URL")  # Your Render URL (e.g., "your-bot-name.onrender.com")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database simulation
free_trial_users = {}
user_sessions = {}
purchased_numbers = {}  # Stores user's purchased numbers: {user_id: [numbers]}
active_subscriptions = {}  # {user_id: expiry_timestamp}

CANADA_AREA_CODES = ['204', '236', '249', '250', '289', '306', '343', '365', '403', '416', '418', '431', '437', '438', '450', '506', '514', '519', '579', '581', '587', '604', '613', '639', '647', '672', '705', '709', '778', '780', '782', '807', '819', '825', '867', '873', '902', '905']

# Helper functions
def extract_canada_numbers(text: str):
    results = set()
    digits_only = re.findall(r'\d{10,11}', text)
    for number in digits_only:
        digits = number[-10:]
        area_code = digits[:3]
        if area_code in CANADA_AREA_CODES:
            formatted = "+1" + digits
            results.add(formatted)
    return list(results)

def check_subscription(user_id):
    expiry = active_subscriptions.get(user_id)
    return expiry and expiry > datetime.now().timestamp()

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    
    if check_subscription(user_id) or free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"{user_name} Subscription চালু আছে এবার Log In করুন", reply_markup=reply_markup)
        return

    keyboard = [
        [InlineKeyboardButton("⬜ 1 Hour - Free 🌸", callback_data="plan_free")],
        [InlineKeyboardButton("🔴 1 Day - 2$", callback_data="plan_1d")],
        [InlineKeyboardButton("🟠 7 Day - 10$", callback_data="plan_7d")],
        [InlineKeyboardButton("🟡 15 Day - 15$", callback_data="plan_15d")],
        [InlineKeyboardButton("🟢 30 Day - 20$", callback_data="plan_30d")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Welcome {user_name} 🌸\n"
        "এই @vimtips_free_earn চ্যানেলে জয়েন করে একটা স্কিনশর্ট নিয়ে @EVANHELPING_BOT এই বটে সেন্ড করুন "
        "তার পর যেকোনো একটা Subscription ক্লিক করুন",
        reply_markup=reply_markup
    )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if check_subscription(user_id) or free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("আপনার Subscription চালু আছে, নিচে Login করুন ⬇️", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not check_subscription(user_id) and free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ আপনার Subscription নেই। প্রথমে Subscription নিন।")
        return

    session = user_sessions.get(user_id)
    if not session or not session.get("logged_in", False):
        await update.message.reply_text("❌ দয়া করে প্রথমে /login দিয়ে Token দিয়ে Log In করুন।")
        return

    args = context.args
    selected_area_codes = []

    if args:
        area_code = args[0]
        if area_code in CANADA_AREA_CODES:
            selected_area_codes = [area_code] * 30
        else:
            await update.message.reply_text("⚠️ আপনার দেওয়া area code পাওয়া যায়নি। অনুগ্রহ করে সঠিক কানাডার area code দিন।")
            return
    else:
        count = min(30, len(CANADA_AREA_CODES))
        selected_area_codes = random.sample(CANADA_AREA_CODES, count)

    phone_numbers = [f"+1{code}{random.randint(1000000, 9999999)}" for code in selected_area_codes]

    message_text = "আপনার নাম্বার গুলো হলো 👇👇\n\n" + "\n".join(phone_numbers)
    buttons = [[InlineKeyboardButton(num, callback_data=f"number_{num}")] for num in phone_numbers]
    buttons.append([InlineKeyboardButton("Cancel ❌", callback_data="cancel_buy")])
    reply_markup = InlineKeyboardMarkup(buttons)

    sent_msg = await update.message.reply_text(message_text, reply_markup=reply_markup)

    async def delete_message():
        await asyncio.sleep(300)
        try:
            await sent_msg.delete()
        except:
            pass

    asyncio.create_task(delete_message())

async def my_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    numbers = purchased_numbers.get(user_id, [])
    
    if not numbers:
        await update.message.reply_text("❌ আপনি এখনো কোনো নাম্বার কিনেননি।")
        return
    
    message = "আপনার কেনা নাম্বারগুলো:\n\n" + "\n".join(numbers)
    await update.message.reply_text(message)

# Callback handler
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    username = query.from_user.username or "N/A"

    if query.data == "plan_free":
        if free_trial_users.get(user_id):
            await query.edit_message_text("⚠️ আপনি এরই মধ্যে Free Trial ব্যবহার করেছেন।")
        else:
            free_trial_users[user_id] = "active"
            await query.message.delete()
            await context.bot.send_message(chat_id=user_id, text="✅ আপনার Free Trial Subscription টি চালু হয়েছে")

            async def revoke():
                await asyncio.sleep(3600)
                free_trial_users.pop(user_id, None)
                await context.bot.send_message(chat_id=user_id, text="🌻 আপনার Free Trial টি শেষ হতে যাচ্ছে")
            asyncio.create_task(revoke())

    elif query.data.startswith("plan_"):
        plan_info = {
            "plan_1d": ("1 Day", "2$", 86400),
            "plan_7d": ("7 Day", "10$", 604800),
            "plan_15d": ("15 Day", "15$", 1296000),
            "plan_30d": ("30 Day", "20$", 2592000)
        }
        duration, price, seconds = plan_info.get(query.data, ("", "", 0))

        text = (
            f"{user_name} {duration} সময়ের জন্য Subscription নিতে চাচ্ছে।\n\n"
            f"🔆 User Name : {user_name}\n"
            f"🔆 User ID : {user_id}\n"
            f"🔆 Username : @{username}"
        )
        buttons = [
            [InlineKeyboardButton("APPRUVE ✅", callback_data=f"approve_{user_id}_{seconds}"),
            InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        await query.message.delete()
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=reply_markup)

        payment_msg = (
            f"Please send {price} to Binance Pay ID: \n"
            "পেমেন্ট করে প্রমান হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490\n\n"
            f"Your payment details:\n"
            f"🆔 User ID: {user_id}\n"
            f"👤 Username: @{username}\n"
            f"📋 Plan: {duration}\n"
            f"💰 Amount: {price}"
        )
        await context.bot.send_message(chat_id=user_id, text=payment_msg)

    elif query.data == "login":
        await context.bot.send_message(
            chat_id=user_id,
            text="আপনার Sid এবং Auth Token দিন 🎉\n\nব্যবহার হবে: `<sid> <auth>`",
            parse_mode='Markdown'
        )

    elif query.data.startswith("approve_"):
        _, uid, seconds = query.data.split("_")
        uid = int(uid)
        seconds = int(seconds)
        
        expiry = datetime.now().timestamp() + seconds
        active_subscriptions[uid] = expiry
        
        expiry_date = datetime.fromtimestamp(expiry).strftime("%Y-%m-%d %H:%M:%S")
        await context.bot.send_message(
            chat_id=uid,
            text=f"✅ আপনার Subscription চালু করা হয়েছে\nExpiry: {expiry_date}"
        )
        await query.edit_message_text("✅ Approve করা হয়েছে এবং Permission দেওয়া হয়েছে।")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription Request বাতিল করা হয়েছে।")

    elif query.data == "cancel_buy":
        await query.edit_message_text("নাম্বার কিনা বাতিল হয়েছে ☢️")

    elif query.data.startswith("number_"):
        selected_number = query.data[len("number_"):]
        buy_button = InlineKeyboardMarkup([[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{selected_number}")]])
        await context.bot.send_message(chat_id=user_id, text=f"{selected_number}", reply_markup=buy_button)

    elif query.data.startswith("buy_number_"):
        number_to_buy = query.data[len("buy_number_"):]
        session = user_sessions.get(user_id)
        
        if not session or not session.get("logged_in", False):
            await context.bot.send_message(chat_id=user_id, text="❌ দয়া করে প্রথমে /login দিয়ে Token দিয়ে Log In করুন।")
            return

        sid = session.get("sid")
        auth = session.get("auth")

        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session_http:
            try:
                # Get account balance first
                balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
                async with session_http.get(balance_url) as balance_resp:
                    if balance_resp.status != 200:
                        await context.bot.send_message(chat_id=user_id, text="❌ ব্যালেন্স চেক করতে সমস্যা হয়েছে। টোকেন ভ্যালিড নয় বা অন্য কোনো সমস্যা।")
                        return
                    
                    balance_data = await balance_resp.json()
                    initial_balance = float(balance_data.get("balance", 0.0))
                    currency = balance_data.get("currency", "USD")

                # Get available phone numbers in the area code
                area_code = number_to_buy[2:5]
                available_numbers_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/AvailablePhoneNumbers/CA/Local.json?AreaCode={area_code}"
                
                async with session_http.get(available_numbers_url) as numbers_resp:
                    if numbers_resp.status != 200:
                        await context.bot.send_message(chat_id=user_id, text="❌ এই এরিয়া কোডে নাম্বার পাওয়া যায়নি। অন্য এরিয়া কোড ট্রাই করুন।")
                        return
                    
                    numbers_data = await numbers_resp.json()
                    if not numbers_data.get('available_phone_numbers'):
                        await context.bot.send_message(chat_id=user_id, text="❌ এই এরিয়া কোডে কোনো নাম্বার অবশিষ্ট নেই।")
                        return
                    
                    # Select the first available number
                    selected_number = numbers_data['available_phone_numbers'][0]['phone_number']
                    number_cost = float(numbers_data['available_phone_numbers'][0].get('price', 1.0))

                # Check if balance is sufficient
                if initial_balance < number_cost:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"❌ আপনার ব্যালেন্স পর্যাপ্ত নয়।\nনাম্বার মূল্য: ${number_cost:.2f}\nআপনার ব্যালেন্স: ${initial_balance:.2f}"
                    )
                    return

                # Purchase the number with proper webhook
                purchase_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json"
                purchase_data = {
                    "PhoneNumber": selected_number,
                    "SmsUrl": f"https://{RENDER_URL}/twilio-webhook/{user_id}",
                    "SmsMethod": "POST",
                    "StatusCallback": f"https://{RENDER_URL}/twilio-status/{user_id}",
                    "StatusCallbackMethod": "POST"
                }
                
                async with session_http.post(purchase_url, data=purchase_data) as purchase_resp:
                    if purchase_resp.status != 201:
                        error_data = await purchase_resp.json()
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"❌ নাম্বার কেনা সম্ভব হয়নি: {error_data.get('message', 'Unknown error')}"
                        )
                        return
                    
                    purchase_result = await purchase_resp.json()

                # Store purchased number
                if user_id not in purchased_numbers:
                    purchased_numbers[user_id] = []
                purchased_numbers[user_id].append(selected_number)

                # Get updated balance
                async with session_http.get(balance_url) as updated_balance_resp:
                    updated_balance_data = await updated_balance_resp.json()
                    new_balance = float(updated_balance_data.get("balance", initial_balance - number_cost))

                # Send success message
                success_msg = (
                    f"✅ সফলভাবে নাম্বার কেনা হয়েছে!\n\n"
                    f"📞 নাম্বার: {selected_number}\n"
                    f"💵 মূল্য: ${number_cost:.2f}\n"
                    f"💰 নতুন ব্যালেন্স: ${new_balance:.2f}\n\n"
                    f"এই নাম্বারে মেসেজ পেতে নিচের বাটন ক্লিক করুন 👇"
                )
                
                buttons = [
                    [InlineKeyboardButton("📨 মেসেজ চেক করুন", callback_data=f"message_{selected_number}")],
                    [InlineKeyboardButton("🔄 আরেকটি নাম্বার কিনুন", callback_data="buy_another")]
                ]
                reply_markup = InlineKeyboardMarkup(buttons)
                
                await query.edit_message_text(success_msg, reply_markup=reply_markup)

            except Exception as e:
                logger.error(f"Error during number purchase: {str(e)}")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ নাম্বার কেনার সময় ত্রুটি হয়েছে: {str(e)}"
                )

    elif query.data.startswith("message_"):
        selected_number = query.data[len("message_"):]
        session = user_sessions.get(user_id)
        if not session or not session.get("logged_in", False):
            await context.bot.send_message(chat_id=user_id, text="❌ দয়া করে প্রথমে /login দিয়ে Token দিয়ে Log In করুন।")
            return

        sid = session.get("sid")
        auth = session.get("auth")

        try:
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session_http:
                sms_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?To={selected_number}"
                async with session_http.get(sms_url) as resp:
                    data = await resp.json()
                    messages = data.get("messages", [])

                    if messages:
                        latest = messages[0]
                        body = latest.get("body", "❓ কোন কন্টেন্ট নেই")
                        from_number = latest.get("from", "Unknown")

                        new_text = (
                            f"📨 নতুন মেসেজ পাওয়া গেছে ✅\n\n"
                            f"🔸 From: {from_number}\n"
                            f"🔸 Body: {body}"
                        )
                        await query.edit_message_text(new_text)
                    else:
                        original_text = query.message.text
                        await query.edit_message_text("No message received ❌")

                        async def revert_text():
                            await asyncio.sleep(5)
                            try:
                                await query.message.edit_text(original_text, reply_markup=query.message.reply_markup)
                            except:
                                pass

                        asyncio.create_task(revert_text())
        except Exception as e:
            logger.error(f"Message fetch error: {e}")
            await context.bot.send_message(chat_id=user_id, text="🚫 মেসেজ পড়তে সমস্যা হয়েছে, পরে চেষ্টা করুন।")

    elif query.data == "buy_another":
        await buy_command(query.message, context)

# Message handler
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_subscription(user_id) and free_trial_users.get(user_id) != "active":
        return

    text = update.message.text.strip()

    if " " in text:
        try:
            sid, auth = text.split(" ", 1)
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
                async with session.get("https://api.twilio.com/2010-04-01/Accounts.json") as resp:
                    if resp.status == 401:
                        await update.message.reply_text("🎃 টোকেন Suspend হয়ে গেছে অন্য টোকেন ব্যবহার করুন")
                        return
                    data = await resp.json()
                    account_name = data['accounts'][0]['friendly_name']
                    balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"

                async with session.get(balance_url) as b:
                    balance_data = await b.json()
                    balance = float(balance_data.get("balance", 0.0))
                    currency = balance_data.get("currency", "USD")

                    if currency != "USD":
                        rate_url = f"https://open.er-api.com/v6/latest/{currency}"
                        async with session.get(rate_url) as rate_resp:
                            rates = await rate_resp.json()
                            usd_rate = rates["rates"].get("USD", 1)
                            balance *= usd_rate

                    user_sessions[user_id] = {"sid": sid, "auth": auth, "logged_in": True}

                    await update.message.reply_text(
                        f"🎉 𝐋𝐨𝐠 𝐈𝐧 𝐒𝐮𝐜𝐜𝐞𝐬𝐬𝐟𝐮𝐥🎉\n\n"
                        f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗡𝗮𝗺𝗲 : {account_name}\n"
                        f"⭕ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲 : ${balance:.2f}\n\n"
                        f"বিঃদ্রঃ নাম্বার কিনার আগে ব্যালেন্স চেক করে নিবেন ♻️\n\n"
                        f"Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁"
                    )
                    return
        except Exception as e:
            logger.error(f"Login error: {str(e)}")

    numbers_found = extract_canada_numbers(text)
    if not numbers_found:
        return

    for number in numbers_found:
        buy_button = InlineKeyboardMarkup([[InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{number}")]])
        await update.message.reply_text(f"আপনার দেওয়া নাম্বারটি শনাক্ত হলো:\n{number}", reply_markup=buy_button)

# Twilio webhook handlers
async def handle_twilio_webhook(request):
    user_id = request.match_info['user_id']
    data = await request.post()
    
    message_body = data.get('Body', '')
    from_number = data.get('From', '')
    to_number = data.get('To', '')
    
    logger.info(f"Received message from {from_number} to {to_number}: {message_body}")
    
    try:
        message_text = (
            f"📨 নতুন মেসেজ এসেছে!\n\n"
            f"📞 থেকে: {from_number}\n"
            f"📞 নাম্বারে: {to_number}\n"
            f"✉️ মেসেজ: {message_body}"
        )
        
        await application.bot.send_message(
            chat_id=user_id,
            text=message_text
        )
    except Exception as e:
        logger.error(f"Failed to forward message to user {user_id}: {str(e)}")
    
    return web.Response(text="<Response></Response>", content_type="text/xml")

async def handle_twilio_status(request):
    user_id = request.match_info['user_id']
    data = await request.post()
    logger.info(f"Status update for user {user_id}: {data}")
    return web.Response(text="OK")

# Main application setup
application = Application.builder().token(BOT_TOKEN).build()

# Add handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("login", login_command))
application.add_handler(CommandHandler("buy", buy_command))
application.add_handler(CommandHandler("mynumbers", my_numbers))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

async def main():
    await application.initialize()
    await application.start()
    app = web.Application()
    
    # Telegram webhook
    app.router.add_post(f"/{BOT_TOKEN}", handle_update)
    
    # Twilio webhooks
    app.router.add_post("/twilio-webhook/{user_id}", handle_twilio_webhook)
    app.router.add_post("/twilio-status/{user_id}", handle_twilio_status)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Bot is running with Twilio webhooks...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
