import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters
import logging
import pytz

# লগিং কনফিগারেশন
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ডাটাবেস হিসাবে একটি ডিকশনারি ব্যবহার করা হচ্ছে (প্রোডাকশনে ডাটাবেস ব্যবহার করুন)
users_db = {}
free_trial_used = set()
ADMIN_CHAT_ID = "6165060012"  # এডমিনের চ্যাট আইডি এখানে সেট করুন

# বট টোকেন (Render এ environment variable থেকে নেবে)
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# প্ল্যানের ডেটা
PLANS = {
    '1h': {'duration': timedelta(hours=1), 'price': 0, 'text': '1 Hour - Free 🌸'},
    '1d': {'duration': timedelta(days=1), 'price': 2, 'text': '1 Day - 2$'},
    '7d': {'duration': timedelta(days=7), 'price': 10, 'text': '7 Day - 10$'},
    '15d': {'duration': timedelta(days=15), 'price': 15, 'text': '15 Day - 15$'},
    '30d': {'duration': timedelta(days=30), 'price': 20, 'text': '30 Day - 20$'}
}

# স্টার্ট কমান্ড হ্যান্ডলার
def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    
    # ইউজার ডাটাবেসে আছে কিনা চেক করুন
    if user_id in users_db and users_db[user_id]['subscription_end'] > datetime.now(pytz.utc):
        # সাবস্ক্রিপশন সক্রিয় আছে
        update.message.reply_text(
            f'স্বাগতম {user.full_name} আপনার Subscription চালু আছে টোকেন দিয়ে Login করুন\n'
            'Login করতে /Login কমান্ড ব্যবহার করুন'
        )
    else:
        # সাবস্ক্রিপশন সক্রিয় নেই
        keyboard = [
            [
                InlineKeyboardButton(PLANS['1h']['text'], callback_data='plan_1h'),
                InlineKeyboardButton(PLANS['1d']['text'], callback_data='plan_1d')
            ],
            [
                InlineKeyboardButton(PLANS['7d']['text'], callback_data='plan_7d'),
                InlineKeyboardButton(PLANS['15d']['text'], callback_data='plan_15d')
            ],
            [
                InlineKeyboardButton(PLANS['30d']['text'], callback_data='plan_30d')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            'আপনার Subscriptions চালু নেই ♻️\n'
            'চালু করার জন্য নিচের Subscription Choose করুন ✅',
            reply_markup=reply_markup
        )

# ক্যালব্যাক কুয়েরি হ্যান্ডলার (বাটন ক্লিক)
def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user = update.effective_user
    user_id = str(user.id)
    
    if query.data.startswith('plan_'):
        plan_key = query.data.split('_')[1]
        plan = PLANS[plan_key]
        
        # ফ্রি ট্রায়াল চেক
        if plan_key == '1h' and user_id in free_trial_used:
            query.edit_message_text(text='আপনি ইতিমধ্যে ফ্রি ট্রায়াল ব্যবহার করেছেন। অন্য প্ল্যান নির্বাচন করুন।')
            return
        
        # ফ্রি প্ল্যান হলে সরাসরি অ্যাক্টিভেট করুন
        if plan_key == '1h':
            # ফ্রি ট্রায়াল মার্ক করুন
            free_trial_used.add(user_id)
            
            # সাবস্ক্রিপশন অ্যাক্টিভেট করুন
            subscription_end = datetime.now(pytz.utc) + plan['duration']
            users_db[user_id] = {
                'name': user.full_name,
                'username': user.username,
                'subscription_end': subscription_end,
                'plan': plan_key
            }
            
            query.edit_message_text(text=f'আপনার ১ ঘন্টার ফ্রি ট্রায়াল সক্রিয় করা হয়েছে! এটি {subscription_end} এ শেষ হবে।')
            return
        
        # পেইড প্ল্যানের জন্য পেমেন্ট তথ্য পাঠান
        payment_message = (
            f'Please send ${plan["price"]} to Binance Pay ID:\n'
            'পেমেন্ট করে প্রমান হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490\n\n'
            f'Your payment details:\n'
            f'❄️ Name : {user.full_name}\n'
            f'🆔 User ID: `{user.id}`\n'
            f'👤 Username: @{user.username}\n'
            f'📋 Plan: {plan["text"]}\n'
            f'💰 Amount: ${plan["price"]}'
        )
        
        query.edit_message_text(text=payment_message, parse_mode='Markdown')
        
        # এডমিনকে নোটিফাই করুন
        admin_keyboard = [
            [
                InlineKeyboardButton("Approve ✅", callback_data=f'approve_{user_id}_{plan_key}'),
                InlineKeyboardButton("Cancel ❌", callback_data=f'cancel_{user_id}')
            ]
        ]
        admin_reply_markup = InlineKeyboardMarkup(admin_keyboard)
        
        context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f'{user.full_name} {plan["text"]} সময়ের জন্য Subscription নিতে চাচ্ছে।\n\n'
                f'🔆 User Name : {user.full_name}\n'
                f'🔆 User ID : {user.id}\n'
                f'🔆 Username : @{user.username}'
            ),
            reply_markup=admin_reply_markup
        )
    
    elif query.data.startswith('approve_'):
        # এডমিন অ্যাপ্রুভ করলে
        _, user_id, plan_key = query.data.split('_')
        plan = PLANS[plan_key]
        
        # সাবস্ক্রিপশন অ্যাক্টিভেট করুন
        subscription_end = datetime.now(pytz.utc) + plan['duration']
        users_db[user_id] = {
            'name': users_db.get(user_id, {}).get('name', ''),
            'username': users_db.get(user_id, {}).get('username', ''),
            'subscription_end': subscription_end,
            'plan': plan_key
        }
        
        # এডমিনকে কনফার্মেশন পাঠান
        query.edit_message_text(text=f'Subscription approved for user {user_id}')
        
        # ইউজারকে নোটিফাই করুন
        context.bot.send_message(
            chat_id=user_id,
            text=f'আপনার সাবস্ক্রিপশন সক্রিয় করা হয়েছে! এটি {subscription_end} এ শেষ হবে।'
        )
    
    elif query.data.startswith('cancel_'):
        # এডমিন ক্যান্সেল করলে
        _, user_id = query.data.split('_')
        
        # এডমিনকে কনফার্মেশন পাঠান
        query.edit_message_text(text=f'Subscription request canceled for user {user_id}')
        
        # ইউজারকে নোটিফাই করুন
        context.bot.send_message(
            chat_id=user_id,
            text='আপনার সাবস্ক্রিপশন রিকোয়েস্ট বাতিল করা হয়েছে।'
        )

# এরর হ্যান্ডলার
def error(update: Update, context: CallbackContext) -> None:
    logger.warning('Update "%s" caused error "%s"', update, context.error)

# মেইন ফাংশন
def main() -> None:
    # আপডেটার তৈরি করুন এবং ডিসপ্যাচারে যোগ করুন
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # কমান্ড হ্যান্ডলার
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(button))
    
    # লগ সব errors
    dispatcher.add_error_handler(error)

    # বট শুরু করুন
    updater.start_polling()
    
    # বট চালু রাখুন Ctrl+C পর্যন্ত
    updater.idle()

if __name__ == '__main__':
    main()
