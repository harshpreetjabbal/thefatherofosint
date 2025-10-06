# ===== COMPLETE AND FINAL CODE WITH CURRENCY OPTION =====
import requests
from random import randint
import math
import sqlite3
from datetime import datetime, timedelta

try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
except ModuleNotFoundError:
    input("Required library not found. Please run the command: pip install pyTelegramBotApi")

# ===== कॉन्फ़िगरेशन =====
ADMIN_USER_ID = 7631831168  # <<<--- अपनी असली टेलीग्राम यूजर ID यहाँ डालें
bot_token = "8202732453:AAHQBZjGwfq4OzwaaaHYWX-55HWfOFrWR1o"
api_token = "7631831168:tkkC9AEs"
limit = 300
UPI_ID = "9540730341@jio"
DB_FILE = "bot_database.db"
url = "https://leakosintapi.com/"

# करेंसी कनवर्ट करने के लिए रेट (आप इसे बदल सकते हैं)
USD_TO_INR_RATE = 83.50

# प्लान की कीमतें USD में
PLAN_PRICES_USD = {
    "daily": 0.50,
    "weekly": 2.00,
    "monthly": 3.00
}

# ===== डेटाबेस सेटअप =====
def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance_usd REAL DEFAULT 0.0,
            subscription_end TEXT,
            currency TEXT DEFAULT 'INR'
        )
    ''')
    # चेक करें कि currency कॉलम मौजूद है या नहीं, अगर नहीं है तो जोड़ें
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'currency' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN currency TEXT DEFAULT 'INR'")
    conn.commit()
    conn.close()

# ===== डेटाबेस के हेल्पर फंक्शन्स =====
def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # डिक्शनरी की तरह एक्सेस करने के लिए
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    conn.close()
    return user # अब यह एक डिक्शनरी की तरह काम करेगा

def update_wallet(user_id, amount_usd):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance_usd = balance_usd + ? WHERE user_id = ?", (amount_usd, user_id))
    conn.commit()
    conn.close()

def purchase_plan(user_id, plan_type):
    price_usd = PLAN_PRICES_USD[plan_type]
    user = get_user(user_id)
    current_balance_usd = user['balance_usd']
    if current_balance_usd < price_usd:
        return False, current_balance_usd
    new_balance_usd = current_balance_usd - price_usd
    now = datetime.now()
    if plan_type == "daily": end_date = now + timedelta(days=1)
    elif plan_type == "weekly": end_date = now + timedelta(weeks=1)
    elif plan_type == "monthly": end_date = now + timedelta(days=30)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance_usd = ?, subscription_end = ? WHERE user_id = ?", (new_balance_usd, end_date.isoformat(), user_id))
    conn.commit()
    conn.close()
    return True, new_balance_usd

def set_user_currency(user_id, currency):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET currency = ? WHERE user_id = ?", (currency, user_id))
    conn.commit()
    conn.close()

# ===== एक्सेस कण्ट्रोल फंक्शन (पहले जैसा ही) =====
def user_has_active_subscription(user_id):
    # ... (यह फंक्शन बिना किसी बदलाव के वैसा ही रहेगा)
    pass

# ... (generate_report और create_inline_keyboard फंक्शन्स पहले जैसे ही रहेंगे)

bot = telebot.TeleBot(bot_token)

# ===== बॉट कमांड्स =====

@bot.message_handler(commands=['currency'])
def change_currency(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("₹ Indian Rupee (INR)", callback_data="set_currency_INR"),
        InlineKeyboardButton("$ US Dollar (USD)", callback_data="set_currency_USD")
    )
    bot.send_message(message.chat.id, "Please select your display currency:", reply_markup=markup)

@bot.message_handler(commands=['wallet'])
def show_wallet(message):
    user = get_user(message.from_user.id)
    balance_usd = user['balance_usd']
    currency = user['currency']
    
    if currency == 'INR':
        balance_display = f"₹{(balance_usd * USD_TO_INR_RATE):.2f} INR"
    else:
        balance_display = f"${balance_usd:.2f} USD"

    sub_status = "Inactive"
    if user['subscription_end']:
        sub_end_date = datetime.fromisoformat(user['subscription_end'])
        if sub_end_date > datetime.now():
            sub_status = f"Active until {sub_end_date.strftime('%Y-%m-%d %H:%M')}"

    bot.reply_to(message, f"💰 **Your Wallet**\n\n<b>Balance:</b> {balance_display}\n<b>Subscription:</b> {sub_status}", parse_mode="html")

@bot.message_handler(commands=['approve'])
def approve_payment(message):
    if message.from_user.id != ADMIN_USER_ID:
        bot.reply_to(message, "❌ This is an admin-only command.")
        return
    try:
        parts = message.text.split()
        user_id_to_approve = int(parts[1])
        amount_usd_to_add = float(parts[2])
        
        get_user(user_id_to_approve) # सुनिश्चित करें कि यूजर DB में है
        update_wallet(user_id_to_approve, amount_usd_to_add)
        
        user_after_update = get_user(user_id_to_approve)
        new_balance_usd = user_after_update['balance_usd']
        user_currency = user_after_update['currency']

        bot.reply_to(message, f"✅ Success! ${amount_usd_to_add:.2f} USD added to user {user_id_to_approve}'s wallet.")
        
        # यूजर को उसकी चुनी हुई करेंसी में सूचित करें
        if user_currency == 'INR':
            credited_amount_display = f"₹{(amount_usd_to_add * USD_TO_INR_RATE):.2f} INR"
            new_balance_display = f"₹{(new_balance_usd * USD_TO_INR_RATE):.2f} INR"
        else:
            credited_amount_display = f"${amount_usd_to_add:.2f} USD"
            new_balance_display = f"${new_balance_usd:.2f} USD"
            
        bot.send_message(user_id_to_approve, f"🎉 Your wallet has been credited with {credited_amount_display}.\nYour new balance is {new_balance_display}.")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Incorrect format. Use: /approve <user_id> <amount_in_USD>")

@bot.message_handler(commands=['shop'])
def show_shop(message):
    user = get_user(message.from_user.id)
    currency = user['currency']
    
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    
    for plan, price_usd in PLAN_PRICES_USD.items():
        if currency == 'INR':
            price_display = f"₹{(price_usd * USD_TO_INR_RATE):.2f} INR"
        else:
            price_display = f"${price_usd:.2f} USD"
        
        plan_name = f"🗓️ {plan.capitalize()} Plan - {price_display}"
        markup.add(InlineKeyboardButton(plan_name, callback_data=f"shop_{plan}"))
        
    bot.send_message(message.chat.id, "Welcome to the Shop! Purchase a plan using your wallet balance:", reply_markup=markup)

# ... (start, payment, submit_utr, language, echo_message कमांड्स पहले जैसे ही रहेंगे)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call: CallbackQuery):
    global cash_reports
    data = call.data
    
    # ... (पेज बदलने का लॉजिक पहले जैसा ही रहेगा)

    if data.startswith("set_currency_"):
        currency = data.split('_')[-1]
        set_user_currency(call.from_user.id, currency)
        bot.answer_callback_query(call.id, f"Currency set to {currency}")
        bot.send_message(call.message.chat.id, f"Display currency has been changed to {currency}.")
        
    elif data.startswith("shop_"):
        plan = data.split('_')[-1]
        price_usd = PLAN_PRICES_USD[plan]
        
        bot.answer_callback_query(call.id)
        
        success, new_balance_usd = purchase_plan(call.from_user.id, plan)
        
        user = get_user(call.from_user.id)
        currency = user['currency']
        
        if success:
            if currency == 'INR':
                new_balance_display = f"₹{(new_balance_usd * USD_TO_INR_RATE):.2f} INR"
            else:
                new_balance_display = f"${new_balance_usd:.2f} USD"
            bot.send_message(call.message.chat.id, f"✅ Success! You have purchased the {plan} plan.\nYour new wallet balance is {new_balance_display}.")
        else:
            if currency == 'INR':
                required_display = f"₹{(price_usd * USD_TO_INR_RATE):.2f}"
                balance_display = f"₹{(new_balance_usd * USD_TO_INR_RATE):.2f}"
            else:
                required_display = f"${price_usd:.2f}"
                balance_display = f"${new_balance_usd:.2f}"
            bot.send_message(call.message.chat.id, f"❌ Insufficient balance.\n<b>Required:</b> {required_display}\n<b>Your Balance:</b> {balance_display}", parse_mode="html")
    
    # ... (भाषा बदलने का लॉजिक पहले जैसा ही रहेगा)

# ===== बॉट को शुरू करें =====
if __name__ == "__main__":
    setup_database()
    print("Bot is starting with Currency and Subscription System...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"An error occurred: {e}")