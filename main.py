import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
import sqlite3
from datetime import datetime, timedelta
import pytz

# কনফিগারেশন
ADMIN_CHAT_ID = "6165060012"  # আপনার টেলিগ্রাম চ্যাট আইডি দিন এখানে
BOT_TOKEN = "7938926278:AAFRUMnq968-gcd4z9mV04cGGyu2v2X6bvE"  # আপনার বট টোকেন দিন এখানে

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ডেটাবেস ফাংশন
def init_db():
    conn = sqlite3.connect('subscription_bot.db')
    cursor = conn.cursor()
    
    # ইউজার টেবিল
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        subscription_type TEXT,
        subscription_start TEXT,
        subscription_end TEXT,
        free_trial_used INTEGER DEFAULT 0
    )
    ''')
    
    # পেমেন্ট রিকোয়েস্ট টেবিল
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payment_requests (
        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan TEXT,
        amount REAL,
        status TEXT DEFAULT 'pending',
        request_time TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('subscription_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user(user_id, **kwargs):
    conn = sqlite3.connect('subscription_bot.db')
    cursor = conn.cursor()
    
    set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    
    cursor.execute(f'''
    UPDATE users 
    SET {set_clause}
    WHERE user_id = ?
    ''', values)
    
    conn.commit()
    conn.close()

def add_payment_request(user_id, plan, amount):
    conn = sqlite3.connect('subscription_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO payment_requests (user_id, plan, amount)
    VALUES (?, ?, ?)
    ''', (user_id, plan, amount))
    
    conn.commit()
    request_id = cursor.lastrowid
    conn.close()
    return request_id

def update_payment_status(request_id, status):
    conn = sqlite3.connect('subscription_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    UPDATE payment_requests
    SET status = ?
    WHERE request_id = ?
    ''', (status, request_id))
    
    conn.commit()
    conn.close()

# সাবস্ক্রিপশন চেক ফাংশন
def has_active_subscription(user_id):
    user = get_user(user_id)
    if user and user[5]:  # subscription_end
        now = datetime.now(pytz.utc)
        subscription_end = datetime.strptime(user[5], '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
        return subscription_end > now
    return False

# কমান্ড হ্যান্ডলার
def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    username = user.username or "N/A"
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    
    # ইউজার ডেটাবেসে অ্যাড/আপডেট করুন
    conn = sqlite3.connect('subscription_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
    VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name))
    conn.commit()
    conn.close()
    
    if has_active_subscription(user_id):
        update.message.reply_text(
            f'স্বাগতম {full_name} আপনার Subscription চালু আছে টোকেন দিয়ে Login করুন\n'
            'Login করতে /Login কমান্ড ব্যবহার করুন'
        )
    else:
        keyboard = [
            [InlineKeyboardButton("⬜ 1 Hour - Free 🌸", callback_data='free_trial')],
            [InlineKeyboardButton("🔴 1 Day - 2$", callback_data='1_day')],
            [InlineKeyboardButton("🟠 7 Day - 10$", callback_data='7_day')],
            [InlineKeyboardButton("🟡 15 Day - 15$", callback_data='15_day')],
            [InlineKeyboardButton("🟢 30 Day - 20$", callback_data='30_day')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(
            'আপনার Subscriptions চালু নেই ♻️ চালু করার জন্য নিচের Subscription Choose করুন ✅',
            reply_markup=reply_markup
        )

# বাটন হ্যান্ডলার
def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user = query.from_user
    user_id = user.id
    username = user.username or "N/A"
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    full_name = f"{first_name} {last_name}".strip()
    
    if query.data == 'free_trial':
        # ফ্রি ট্রায়াল লজিক
        user_data = get_user(user_id)
        if user_data and user_data[7]:  # free_trial_used
            query.edit_message_text(text="আপনি ইতিমধ্যে ফ্রি ট্রায়াল ব্যবহার করেছেন। অন্য প্যাকেজ নির্বাচন করুন।")
        else:
            # ফ্রি ট্রায়াল অ্যাক্টিভেট করুন
            subscription_end = datetime.now() + timedelta(hours=1)
            update_user(
                user_id,
                subscription_type='1 Hour Free',
                subscription_start=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                subscription_end=subscription_end.strftime('%Y-%m-%d %H:%M:%S'),
                free_trial_used=1
            )
            query.edit_message_text(
                text=f"আপনার 1 ঘন্টার ফ্রি ট্রায়াল সক্রিয় করা হয়েছে! "
                     f"{subscription_end.strftime('%Y-%m-%d %H:%M:%S')} পর্যন্ত সক্রিয় থাকবে।"
            )
    
    else:
        # পেইড প্যাকেজ হ্যান্ডলিং
        plans = {
            '1_day': {'text': '1 Day', 'amount': 2},
            '7_day': {'text': '7 Days', 'amount': 10},
            '15_day': {'text': '15 Days', 'amount': 15},
            '30_day': {'text': '30 Days', 'amount': 20}
        }
        
        plan = plans.get(query.data)
        if plan:
            # পেমেন্ট রিকোয়েস্ট তৈরি করুন
            request_id = add_payment_request(user_id, plan['text'], plan['amount'])
            
            # ইউজারকে পেমেন্ট ইনস্ট্রাকশন দিন
            message = f'''
Please send ${plan['amount']} to Binance Pay ID: 
পেমেন্ট করে প্রমান হিসাবে Admin এর কাছে স্কিনশর্ট অথবা transaction ID দিন @Mr_Evan3490

Your payment details:
❄️ Name : {full_name}
🆔 User ID: `{user_id}` (কপি করতে ক্লিক করুন)
👤 Username: @{username}
📋 Plan: {plan['text']}
💰 Amount: ${plan['amount']}
'''
            query.edit_message_text(text=message, parse_mode='Markdown')
            
            # অ্যাডমিনকে নোটিফাই করুন
            admin_message = f'''
{full_name} {plan['text']} সময়ের জন্য Subscription নিতে চাচ্ছে।

🔆 User Name : {full_name}
🔆 User ID : {user_id}
🔆 Username : @{username}
🔆 Plan : {plan['text']}
🔆 Amount : ${plan['amount']}
'''
            keyboard = [
                [
                    InlineKeyboardButton("Approve ✅", callback_data=f'approve_{request_id}'),
                    InlineKeyboardButton("Cancel ❌", callback_data=f'cancel_{request_id}')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_message,
                reply_markup=reply_markup
            )

# অ্যাডমিন অ্যাকশন হ্যান্ডলার
def admin_action_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data.split('_')
    action = data[0]
    request_id = int(data[1])
    
    # পেমেন্ট রিকোয়েস্ট ডিটেইলস নিন
    conn = sqlite3.connect('subscription_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT pr.*, u.first_name, u.last_name, u.username 
    FROM payment_requests pr
    JOIN users u ON pr.user_id = u.user_id
    WHERE pr.request_id = ?
    ''', (request_id,))
    payment_request = cursor.fetchone()
    
    if not payment_request:
        query.edit_message_text(text="Error: Payment request not found")
        conn.close()
        return
    
    user_id = payment_request[1]
    plan = payment_request[2]
    amount = payment_request[3]
    first_name = payment_request[5] or ""
    last_name = payment_request[6] or ""
    full_name = f"{first_name} {last_name}".strip()
    username = payment_request[7] or "N/A"
    
    if action == 'approve':
        # সাবস্ক্রিপশন অ্যাক্টিভেট করুন
        days = int(plan.split()[0])
        subscription_end = datetime.now() + timedelta(days=days)
        
        cursor.execute('''
        UPDATE users 
        SET subscription_type = ?,
            subscription_start = datetime('now'),
            subscription_end = ?
        WHERE user_id = ?
        ''', (plan, subscription_end.strftime('%Y-%m-%d %H:%M:%S'), user_id))
        
        update_payment_status(request_id, 'approved')
        conn.commit()
        
        # ইউজারকে নোটিফাই করুন
        context.bot.send_message(
            chat_id=user_id,
            text=f"আপনার {plan} সাবস্ক্রিপশন সফলভাবে অ্যাক্টিভেট করা হয়েছে! "
                 f"{subscription_end.strftime('%Y-%m-%d %H:%M:%S')} পর্যন্ত সক্রিয় থাকবে।"
        )
        
        query.edit_message_text(
            text=f"✅ Approved: {full_name} এর {plan} সাবস্ক্রিপশন\n"
                 f"User ID: {user_id}\n"
                 f"Username: @{username}"
        )
    
    elif action == 'cancel':
        update_payment_status(request_id, 'cancelled')
        conn.commit()
        
        # ইউজারকে নোটিফাই করুন
        context.bot.send_message(
            chat_id=user_id,
            text=f"আপনার {plan} সাবস্ক্রিপশন রিকোয়েস্ট বাতিল করা হয়েছে।"
        )
        
        query.edit_message_text(
            text=f"❌ Cancelled: {full_name} এর {plan} সাবস্ক্রিপশন\n"
                 f"User ID: {user_id}\n"
                 f"Username: @{username}"
        )
    
    conn.close()

def main():
    # ডেটাবেস ইনিশিয়ালাইজ করুন
    init_db()
    
    # আপডেটার তৈরি করুন
    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher
    
    # হ্যান্ডলার রেজিস্টার করুন
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CallbackQueryHandler(button_handler, pattern='^(free_trial|1_day|7_day|15_day|30_day)$'))
    dispatcher.add_handler(CallbackQueryHandler(admin_action_handler, pattern='^(approve|cancel)_\d+$'))
    
    # বট শুরু করুন
    updater.start_polling()
    logger.info("Bot started and polling...")
    updater.idle()

if __name__ == '__main__':
    main()
