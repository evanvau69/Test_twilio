import os
import logging
import asyncio
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import random
import re

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
NUMBER_COST = 1.0  # $1 per number

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Data storage
free_trial_users = {}
user_sessions = {}

# Canada area codes
CANADA_AREA_CODES = [
    '204', '236', '249', '250', '289', '306', '343', '365', '403', '416',
    '418', '431', '437', '438', '450', '506', '514', '519', '579', '581',
    '587', '604', '613', '639', '647', '672', '705', '709', '778', '780',
    '782', '807', '819', '825', '867', '873', '902', '905'
]

async def get_available_numbers(sid, auth, area_code=None):
    """Fetch available numbers from Twilio API"""
    try:
        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
            base_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/AvailablePhoneNumbers/CA/Local.json"
            
            params = {}
            if area_code:
                params['AreaCode'] = area_code
            else:
                params['AreaCode'] = ','.join(random.sample(CANADA_AREA_CODES, 3))
            
            async with session.get(base_url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [num['phone_number'] for num in data.get('available_phone_numbers', [])]
                else:
                    error = await resp.json()
                    logger.error(f"Error fetching numbers: {error}")
                    return []
    except Exception as e:
        logger.error(f"Exception in get_available_numbers: {str(e)}")
        return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"{user_name} Subscription is active. Please login below:",
            reply_markup=reply_markup
        )
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
        f"Welcome {user_name} 🌸\nPlease join our channel and choose a subscription plan:",
        reply_markup=reply_markup
    )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) == "active":
        keyboard = [[InlineKeyboardButton("Login 🔑", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Your subscription is active. Please login below:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ You don't have an active subscription. Please subscribe first.")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if free_trial_users.get(user_id) != "active":
        await update.message.reply_text("❌ You don't have an active subscription. Please subscribe first.")
        return

    session = user_sessions.get(user_id)
    if not session or not session.get("logged_in", False):
        await update.message.reply_text("❌ Please login first using /login command.")
        return

    args = context.args
    area_code = args[0] if args else None

    sid = session.get("sid")
    auth = session.get("auth")

    try:
        # Get available numbers from Twilio
        available_numbers = await get_available_numbers(sid, auth, area_code)
        
        if not available_numbers:
            await update.message.reply_text("⚠️ No available numbers found. Try a different area code.")
            return

        # Show first 30 numbers (or less if not available)
        numbers_to_show = available_numbers[:30]
        
        message_text = "Available numbers from Twilio:\n\n" + "\n".join(numbers_to_show)
        buttons = [[InlineKeyboardButton(num, callback_data=f"number_{num}")] for num in numbers_to_show]
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

    except Exception as e:
        logger.error(f"Error in buy_command: {str(e)}")
        await update.message.reply_text("❌ An error occurred while fetching numbers. Please try again.")

async def delete_existing_numbers(session_http, sid):
    """Delete all existing phone numbers for the account"""
    existing_numbers_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json"
    async with session_http.get(existing_numbers_url) as existing_resp:
        if existing_resp.status == 200:
            existing_data = await existing_resp.json()
            for number in existing_data.get("incoming_phone_numbers", []):
                phone_sid = number.get("sid")
                delete_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers/{phone_sid}.json"
                async with session_http.delete(delete_url) as delete_resp:
                    if delete_resp.status != 204:
                        logger.warning(f"Failed to delete number {phone_sid}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.full_name
    username = query.from_user.username or "N/A"

    if query.data == "plan_free":
        if free_trial_users.get(user_id):
            await query.edit_message_text("⚠️ You've already used your free trial.")
        else:
            free_trial_users[user_id] = "active"
            await query.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ Your free trial subscription is now active"
            )

            async def revoke():
                await asyncio.sleep(3600)
                free_trial_users.pop(user_id, None)
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🌻 Your free trial has expired"
                )
            asyncio.create_task(revoke())

    elif query.data.startswith("plan_"):
        plan_info = {
            "plan_1d": ("1 Day", "2$"),
            "plan_7d": ("7 Day", "10$"),
            "plan_15d": ("15 Day", "15$"),
            "plan_30d": ("30 Day", "20$")
        }
        duration, price = plan_info.get(query.data, ("", ""))

        text = (
            f"{user_name} wants to subscribe for {duration}.\n\n"
            f"🔆 User Name: {user_name}\n"
            f"🔆 User ID: {user_id}\n"
            f"🔆 Username: @{username}"
        )
        buttons = [
            [
                InlineKeyboardButton("APPROVE ✅", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("CANCEL ❌", callback_data=f"cancel_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        await query.message.delete()
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=text,
                reply_markup=reply_markup
            )

        payment_msg = (
            f"Please send {price} to our payment method.\n\n"
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
            text="Please enter your Twilio SID and Auth Token in format: `<SID> <AUTH_TOKEN>`",
            parse_mode='Markdown'
        )

    elif query.data.startswith("approve_"):
        uid = int(query.data.split("_")[1])
        free_trial_users[uid] = "active"
        await context.bot.send_message(
            chat_id=uid,
            text="✅ Your subscription has been activated"
        )
        await query.edit_message_text("✅ Subscription approved.")

    elif query.data.startswith("cancel_"):
        await query.edit_message_text("❌ Subscription request cancelled.")

    elif query.data == "cancel_buy":
        await query.edit_message_text("❌ Number purchase cancelled.")

    elif query.data.startswith("number_"):
        selected_number = query.data[len("number_"):]
        buy_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{selected_number}")]
        ])
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Selected number: {selected_number}",
            reply_markup=buy_button
        )

    elif query.data.startswith("buy_number_"):
        number_to_buy = query.data[len("buy_number_"):]
        session = user_sessions.get(user_id)
        if not session or not session.get("logged_in", False):
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Please login first using /login command."
            )
            return

        sid = session.get("sid")
        auth = session.get("auth")

        try:
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session_http:
                # 1. Delete any existing numbers first
                await delete_existing_numbers(session_http, sid)

                # 2. Check balance
                balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
                async with session_http.get(balance_url) as balance_resp:
                    balance_data = await balance_resp.json()
                    balance = float(balance_data.get("balance", 0.0))
                    currency = balance_data.get("currency", "USD")

                    if currency != "USD":
                        rate_url = "https://api.exchangerate-api.com/v4/latest/USD"
                        async with session_http.get(rate_url) as rate_resp:
                            rates = await rate_resp.json()
                            usd_rate = rates["rates"].get(currency, 1)
                            balance /= usd_rate

                    if balance < NUMBER_COST:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"❌ Insufficient balance. Required: ${NUMBER_COST:.2f}, Available: ${balance:.2f}"
                        )
                        return

                # 3. Purchase new number
                purchase_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json"
                purchase_data = {
                    "PhoneNumber": number_to_buy,
                    "SmsUrl": "https://demo.twilio.com/welcome/sms/reply/",
                    "SmsMethod": "POST"
                }

                headers = {
                    "Content-Type": "application/x-www-form-urlencoded"
                }

                async with session_http.post(
                    purchase_url,
                    data=purchase_data,
                    headers=headers
                ) as purchase_resp:
                    if purchase_resp.status == 201:
                        purchased_data = await purchase_resp.json()
                        phone_sid = purchased_data.get("sid")
                        phone_number = purchased_data.get("phone_number")

                        success_msg = (
                            f"✅ Number purchased successfully!\n\n"
                            f"📞 Number: {phone_number}\n"
                            f"💰 Cost: ${NUMBER_COST:.2f}\n"
                            f"💵 New balance: ${balance - NUMBER_COST:.2f}"
                        )

                        buttons = [
                            [InlineKeyboardButton("📩 Check Messages", callback_data=f"check_msg_{phone_sid}")],
                            [InlineKeyboardButton("❌ Close", callback_data="close_msg")]
                        ]
                        reply_markup = InlineKeyboardMarkup(buttons)

                        await query.message.edit_text(success_msg, reply_markup=reply_markup)
                    else:
                        error_data = await purchase_resp.json()
                        error_msg = error_data.get("message", "Unknown error")
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"❌ Failed to purchase number: {error_msg}"
                        )

        except Exception as e:
            logger.error(f"Error in purchase: {str(e)}")
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ An error occurred during purchase. Please try again."
            )

    elif query.data.startswith("check_msg_"):
        phone_sid = query.data[len("check_msg_"):]
        session = user_sessions.get(user_id)
        if not session or not session.get("logged_in", False):
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Please login first using /login command."
            )
            return

        sid = session.get("sid")
        auth = session.get("auth")

        try:
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session_http:
                # Get phone number details
                phone_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers/{phone_sid}.json"
                async with session_http.get(phone_url) as phone_resp:
                    if phone_resp.status != 200:
                        await query.edit_message_text("❌ Failed to get phone number details")
                        return
                    
                    phone_data = await phone_resp.json()
                    phone_number = phone_data.get("phone_number")

                # Get messages
                messages_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?To={phone_number}"
                async with session_http.get(messages_url) as messages_resp:
                    if messages_resp.status != 200:
                        await query.edit_message_text("❌ Failed to retrieve messages")
                        return
                    
                    messages_data = await messages_resp.json()
                    messages = messages_data.get("messages", [])

                    if messages:
                        message_texts = []
                        for msg in messages[:5]:  # Show last 5 messages
                            body = msg.get("body", "No content")
                            from_num = msg.get("from", "Unknown")
                            date = msg.get("date_created", "Unknown")
                            message_texts.append(
                                f"📨 From: {from_num}\n"
                                f"📅 Date: {date}\n"
                                f"💬 Message: {body}\n"
                                f"──────────────────"
                            )
                        
                        full_text = (
                            f"📱 Number: {phone_number}\n"
                            f"📩 Recent Messages:\n\n" +
                            "\n".join(message_texts)
                        )
                        
                        buttons = [
                            [InlineKeyboardButton("🔄 Refresh", callback_data=f"check_msg_{phone_sid}")],
                            [InlineKeyboardButton("❌ Close", callback_data="close_msg")]
                        ]
                        reply_markup = InlineKeyboardMarkup(buttons)
                        
                        await query.edit_message_text(full_text, reply_markup=reply_markup)
                    else:
                        buttons = [
                            [InlineKeyboardButton("🔄 Refresh", callback_data=f"check_msg_{phone_sid}")],
                            [InlineKeyboardButton("❌ Close", callback_data="close_msg")]
                        ]
                        reply_markup = InlineKeyboardMarkup(buttons)
                        await query.edit_message_text(
                            "📭 No messages found",
                            reply_markup=reply_markup
                        )

        except Exception as e:
            logger.error(f"Error checking messages: {e}")
            await query.edit_message_text("❌ Error checking messages")

    elif query.data == "close_msg":
        await query.message.delete()

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

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if free_trial_users.get(user_id) != "active":
        return

    text = update.message.text.strip()

    # Handle login
    if " " in text:
        try:
            sid, auth = text.split(" ", 1)
            async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, auth)) as session:
                # Verify credentials
                account_url = "https://api.twilio.com/2010-04-01/Accounts.json"
                async with session.get(account_url) as resp:
                    if resp.status == 401:
                        await update.message.reply_text("❌ Invalid credentials. Please check your SID and Auth Token.")
                        return
                    
                    data = await resp.json()
                    account_name = data['accounts'][0]['friendly_name']
                
                # Get balance
                balance_url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json"
                async with session.get(balance_url) as b:
                    balance_data = await b.json()
                    balance = float(balance_data.get("balance", 0.0))
                    currency = balance_data.get("currency", "USD")

                    if currency != "USD":
                        rate_url = "https://api.exchangerate-api.com/v4/latest/USD"
                        async with session.get(rate_url) as rate_resp:
                            rates = await rate_resp.json()
                            usd_rate = rates["rates"].get(currency, 1)
                            balance /= usd_rate

                # Store session
                user_sessions[user_id] = {
                    "sid": sid,
                    "auth": auth,
                    "logged_in": True
                }

                await update.message.reply_text(
                    f"✅ Login successful!\n\n"
                    f"🔹 Account: {account_name}\n"
                    f"🔹 Balance: ${balance:.2f} USD\n\n"
                    f"You can now purchase numbers using /buy command."
                )
                return

        except Exception as e:
            logger.error(f"Login error: {e}")
            await update.message.reply_text("❌ Login failed. Please check your credentials and try again.")
            return

    # Handle number extraction
    numbers_found = extract_canada_numbers(text)
    if numbers_found:
        for number in numbers_found:
            buy_button = InlineKeyboardMarkup([
                [InlineKeyboardButton("Buy 💰", callback_data=f"buy_number_{number}")]
            ])
            await update.message.reply_text(
                f"Detected number: {number}",
                reply_markup=buy_button
            )

async def handle_update(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return web.Response(text="OK")

# Set up application
application = Application.builder().token(BOT_TOKEN).build()

# Add handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("login", login_command))
application.add_handler(CommandHandler("buy", buy_command))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

async def main():
    await application.initialize()
    await application.start()
    
    # Set up webhook
    app = web.Application()
    app.router.add_post(f"/{BOT_TOKEN}", handle_update)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info("Bot is running via webhook...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
