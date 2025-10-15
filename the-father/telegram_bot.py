# ===== COMPLETE AND FINAL CODE WITH ALL FEATURES =====
import requests
from random import randint
import math
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import os

try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
except ModuleNotFoundError:
    input("Required library not found. Please run: pip install pyTelegramBotApi pandas openpyxl")

# ===== CONFIGURATION =====
ADMIN_USER_ID = 7631831168
bot_token = "8202732453:AAHQBZjGwfq4OzwaaaHYWX-55HWfOFrWR1o"
api_token = "8012849407:uXByp3Cn"
limit = 300
DB_FILE = "bot_database.db"
url = "https://leakosintapi.com/"
SUPPORT_USERNAME = "harshpreetjabbal"

# Payment Details
UPI_ID = "9540730341@jio"
PAYPAL_ID = "ammyvirk9829@gmail.com"
CAPITALIST_ACC = "U15390154"

USD_TO_INR_RATE = 83.50
PLAN_PRICES_USD = { "daily": 0.50, "weekly": 2.00, "monthly": 3.00 }
REFERRAL_BONUS_PERCENT = 0.05

# ===== DATABASE SETUP =====
def setup_database():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, balance_usd REAL DEFAULT 0.0,
            subscription_end TEXT, currency TEXT DEFAULT 'INR',
            referral_code TEXT, referred_by INTEGER, first_purchase_made INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            payment_method TEXT NOT NULL, transaction_id TEXT NOT NULL,
            amount_usd REAL, status TEXT DEFAULT 'pending', timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# ===== DATABASE HELPER FUNCTIONS =====
def get_user(user_id):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        free_trial_end_date = (datetime.now() + timedelta(days=7)).isoformat()
        user_referral_code = f"ref{user_id}"
        cursor.execute("INSERT INTO users (user_id, subscription_end, referral_code) VALUES (?, ?, ?)", (user_id, free_trial_end_date, user_referral_code))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    conn.close()
    return user

def update_wallet(user_id, amount_usd):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance_usd = balance_usd + ? WHERE user_id = ?", (amount_usd, user_id))
    conn.commit()
    conn.close()

def purchase_plan(user_id, plan_type):
    price_usd = PLAN_PRICES_USD[plan_type]
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    current_balance_usd = user['balance_usd']
    if current_balance_usd < price_usd:
        conn.close()
        return False, current_balance_usd
    new_balance_usd = current_balance_usd - price_usd
    now = datetime.now()
    if plan_type == "daily": end_date = now + timedelta(days=1)
    elif plan_type == "weekly": end_date = now + timedelta(weeks=7)
    elif plan_type == "monthly": end_date = now + timedelta(days=30)
    is_first_purchase = user['first_purchase_made'] == 0
    cursor.execute("UPDATE users SET balance_usd = ?, subscription_end = ?, first_purchase_made = 1 WHERE user_id = ?", (new_balance_usd, end_date.isoformat(), user_id))
    if is_first_purchase and user['referred_by']:
        referrer_id = user['referred_by']
        bonus = price_usd * REFERRAL_BONUS_PERCENT
        cursor.execute("UPDATE users SET balance_usd = balance_usd + ? WHERE user_id = ?", (bonus, referrer_id))
        try:
            bot.send_message(referrer_id, f"🎉 Congratulations! You've earned a ${bonus:.2f} USD bonus!")
        except Exception as e:
            print(f"Could not notify referrer {referrer_id}: {e}")
    conn.commit()
    conn.close()
    return True, new_balance_usd

def set_user_currency(user_id, currency):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET currency = ? WHERE user_id = ?", (currency, user_id))
    conn.commit()
    conn.close()

def user_has_active_subscription(user_id):
    if user_id == ADMIN_USER_ID: return True
    user = get_user(user_id)
    if not user['subscription_end']: return False
    sub_end_date = datetime.fromisoformat(user['subscription_end'])
    return sub_end_date > datetime.now()

cash_reports = {}
user_languages = {}
def generate_report(query, query_id, user_id):
    global cash_reports, url, api_token, limit, user_languages
    lang = user_languages.get(user_id, 'en')
    data = {"token": api_token, "request": query.split("\n")[0], "limit": limit, "lang": lang}
    try:
        response = requests.post(url, json=data).json()
        if "Error code" in response: return None
        cash_reports[str(query_id)] = []
        if "List" in response and response["List"]:
            for db_name, db_data in response["List"].items():
                text = [f"<b>{db_name}</b>", ""]
                if "InfoLeak" in db_data and db_data["InfoLeak"]: text.append(db_data["InfoLeak"] + "\n")
                if db_name != "No results found" and "Data" in db_data:
                    for item in db_data["Data"]:
                        for key, value in item.items():
                            text.append(f"<b>{key}</b>:  {value}")
                        text.append("")
                text_str = "\n".join(text)
                if len(text_str) > 3500: text_str = text_str[:3400] + "\n\n... (some data truncated)"
                cash_reports[str(query_id)].append(text_str)
        else:
             cash_reports[str(query_id)].append("No results found or invalid response.")
        return cash_reports.get(str(query_id))
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None

def create_inline_keyboard(query_id, page_id, count_page):
    markup = InlineKeyboardMarkup()
    if count_page <= 1: return markup
    page_id = page_id % count_page
    markup.row_width = 3
    markup.add(
        InlineKeyboardButton(text="<<", callback_data=f"/page {query_id} {page_id - 1}"),
        InlineKeyboardButton(text=f"{page_id + 1}/{count_page}", callback_data="page_list"),
        InlineKeyboardButton(text=">>", callback_data=f"/page {query_id} {page_id + 1}")
    )
    return markup

bot = telebot.TeleBot(bot_token)
main_menu_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
main_menu_keyboard.row(KeyboardButton("🔍 Search"), KeyboardButton("📋 Menu"))
main_menu_keyboard.row(KeyboardButton("💳 Payment"), KeyboardButton("🛍️ Shop"), KeyboardButton("💰 Wallet"))

# ===== BOT COMMAND HANDLERS =====
@bot.message_handler(commands=["start"])
def send_welcome(message):
    referral_code = message.text.split(' ')[-1] if len(message.text.split(' ')) > 1 else None
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        free_trial_end_date = (datetime.now() + timedelta(days=7)).isoformat()
        user_referral_code = f"ref{user_id}"
        referrer_id = None
        if referral_code and referral_code.startswith('ref'):
            try:
                potential_referrer_id = int(referral_code.replace('ref', ''))
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (potential_referrer_id,))
                if cursor.fetchone():
                    referrer_id = potential_referrer_id
            except ValueError: pass
        cursor.execute("INSERT INTO users (user_id, subscription_end, referral_code, referred_by) VALUES (?, ?, ?, ?)",(user_id, free_trial_end_date, user_referral_code, referrer_id))
        conn.commit()
        if referrer_id:
             bot.send_message(referrer_id, f"🎉 A new user, {message.from_user.first_name}, has joined using your referral link!")
    conn.close()
    bot.reply_to(message, "Hello! I am a Telegram bot that can search databases.", reply_markup=main_menu_keyboard)

@bot.message_handler(commands=['menu'])
def show_main_menu(message):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🗓️ Subscription Validity", callback_data="menu_subscription"),
        InlineKeyboardButton("💰 Wallet Balance", callback_data="menu_wallet"),
        InlineKeyboardButton("💳 Payment Options", callback_data="menu_payment"),
        InlineKeyboardButton("🛍️ Shop", callback_data="menu_shop"),
        InlineKeyboardButton("💱 Change Currency", callback_data="menu_currency"),
        InlineKeyboardButton("🤝 Refer & Earn", callback_data="menu_refer"),
        InlineKeyboardButton("🛠️ Technical Support", url=f"https://t.me/{SUPPORT_USERNAME}")
    )
    bot.send_message(message.chat.id, "Here is the main menu:", reply_markup=markup)

@bot.message_handler(commands=['wallet'])
def show_wallet(message):
    user = get_user(message.from_user.id)
    balance_usd, currency, sub_end_str = user['balance_usd'], user['currency'], user['subscription_end']
    balance_display = f"₹{(balance_usd * USD_TO_INR_RATE):.2f} INR" if currency == 'INR' else f"${balance_usd:.2f} USD"
    sub_status = "Inactive"
    if sub_end_str:
        sub_end_date = datetime.fromisoformat(sub_end_str)
        if sub_end_date > datetime.now(): sub_status = f"Active until {sub_end_date.strftime('%Y-%m-%d %H:%M')}"
    bot.reply_to(message, f"💰 **Your Wallet**\n\n<b>Balance:</b> {balance_display}\n<b>Subscription:</b> {sub_status}", parse_mode="html")

@bot.message_handler(commands=['shop'])
def show_shop(message):
    currency = get_user(message.from_user.id)['currency']
    markup = InlineKeyboardMarkup(row_width=1)
    for plan, price_usd in PLAN_PRICES_USD.items():
        price_display = f"₹{(price_usd * USD_TO_INR_RATE):.2f} INR" if currency == 'INR' else f"${price_usd:.2f} USD"
        markup.add(InlineKeyboardButton(f"▫️ {plan.capitalize()} Plan - {price_display}", callback_data=f"shop_{plan}"))
    bot.send_message(message.chat.id, "Welcome to the Shop! Purchase a plan using your wallet balance:", reply_markup=markup)

@bot.message_handler(commands=['payment'])
def show_payment_options(message):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🇮🇳 UPI", callback_data="pay_upi"),
        InlineKeyboardButton("🅿️ PayPal", callback_data="pay_paypal"),
        InlineKeyboardButton("C Capitalist", callback_data="pay_capitalist")
    )
    bot.send_message(message.chat.id, "Please choose your preferred payment method:", reply_markup=markup)

def generate_excel_report(status, date_filter=None):
    query = "SELECT user_id, payment_method, transaction_id, amount_usd, status, timestamp FROM payments WHERE status = ?"
    params = [status]
    if date_filter:
        query += " AND date(timestamp) = ?"
        params.append(date_filter)
    filename = f"{status}_payments_{date_filter or 'all_time'}.xlsx"
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        if df.empty: return None, "No data found for the specified criteria."
        if 'amount_usd' in df.columns and status == 'approved':
            df['amount_inr'] = df['amount_usd'] * USD_TO_INR_RATE
            df['amount_inr'] = df['amount_inr'].round(2)
        df.to_excel(filename, index=False)
        return filename, None
    except Exception as e: return None, str(e)

@bot.message_handler(commands=['export_pending', 'export_approved'])
def export_command(message):
    if message.from_user.id != ADMIN_USER_ID: return
    status_to_export = 'pending' if 'pending' in message.text else 'approved'
    parts = message.text.split()
    date_filter = parts[1] if len(parts) > 1 else None
    bot.reply_to(message, f"⏳ Generating report for {status_to_export.upper()} payments...")
    excel_file, error = generate_excel_report(status_to_export, date_filter)
    if error:
        bot.send_message(ADMIN_USER_ID, f"Could not generate report: {error}")
        return
    with open(excel_file, 'rb') as doc:
        bot.send_document(ADMIN_USER_ID, doc, caption=f"{status_to_export.capitalize()} Payments Report ({date_filter or 'all time'})")
    if os.path.exists(excel_file): os.remove(excel_file)

@bot.message_handler(commands=['debug_db'])
def debug_db_command(message):
    if message.from_user.id != ADMIN_USER_ID: return
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments ORDER BY id DESC LIMIT 5")
        payments = cursor.fetchall()
        text = "<b>Last 5 Payments:</b>\n"
        if payments:
            for row in payments:
                amount = f"${row['amount_usd']:.2f}" if row['amount_usd'] is not None else "None"
                text += f"- ID:{row['id']} User:{row['user_id']} Method:{row['payment_method']} UTR:{row['transaction_id']} Amt:{amount} Status:<b>{row['status']}</b>\n"
        else:
            text += "No records found.\n"
        conn.close()
        bot.send_message(ADMIN_USER_ID, text, parse_mode="html")
    except Exception as e:
        bot.send_message(ADMIN_USER_ID, f"Error debugging database: {e}")

@bot.message_handler(commands=['approve'])
def approve_payment(message):
    if message.from_user.id != ADMIN_USER_ID:
        bot.reply_to(message, "❌ This is an admin-only command.")
        return
    try:
        parts = message.text.split()
        user_id, amount_inr, payment_id = int(parts[1]), float(parts[2]), int(parts[3])
        amount_usd = amount_inr / USD_TO_INR_RATE
        update_wallet(user_id, amount_usd)
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("UPDATE payments SET status = 'approved', amount_usd = ? WHERE id = ?", (amount_usd, payment_id))
        conn.commit()
        conn.close()
        user_after = get_user(user_id)
        new_balance_usd, currency = user_after['balance_usd'], user_after['currency']
        bot.reply_to(message, f"✅ Success! User {user_id}'s wallet credited with ₹{amount_inr:.2f}.")
        credited_display = f"₹{amount_inr:.2f} INR" if currency == 'INR' else f"${amount_usd:.2f} USD"
        new_balance_display = f"₹{(new_balance_usd * USD_TO_INR_RATE):.2f} INR" if currency == 'INR' else f"${new_balance_usd:.2f} USD"
        bot.send_message(user_id, f"🎉 Your wallet has been credited with {credited_display}.\nYour new balance is {new_balance_display}.")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Incorrect format. Use: /approve <user_id> <amount_in_INR> <payment_id>")

@bot.message_handler(commands=['submit'])
def submit_transaction(message):
    try:
        parts = message.text.split()
        if len(parts) < 3: raise IndexError
        method, transaction_id = parts[1].lower(), " ".join(parts[2:])
        if method not in ['upi', 'paypal', 'capitalist']:
            bot.reply_to(message, "❌ Invalid method. Use 'upi', 'paypal', or 'capitalist'.")
            return
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (user_id, payment_method, transaction_id, status, timestamp) VALUES (?, ?, ?, ?, ?)",
                       (message.from_user.id, method, transaction_id, 'pending', datetime.now().isoformat()))
        payment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        approval_msg = (f"❗️ New Payment Submission\n\n"
                        f"<b>User:</b> {message.from_user.first_name} (ID: <code>{message.from_user.id}</code>)\n"
                        f"<b>Method:</b> {method.upper()}\n"
                        f"<b>Txn ID:</b> <code>{transaction_id}</code>\n\n"
                        f"To approve, reply with:\n"
                        f"<code>/approve {message.from_user.id} AMOUNT_IN_INR {payment_id}</code>")
        bot.send_message(ADMIN_USER_ID, approval_msg, parse_mode="html")
        bot.reply_to(message, "✅ Thank you! Your transaction ID has been submitted for review.")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Incorrect format. Use: `/submit <method> <transaction_id>`", parse_mode="Markdown")

@bot.message_handler(commands=['language'])
def select_language(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en"), InlineKeyboardButton("Русский 🇷🇺", callback_data="set_lang_ru"))
    bot.send_message(message.chat.id, "Please select your preferred search result language:", reply_markup=markup)

@bot.message_handler(commands=['currency'])
def change_currency(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("₹ Indian Rupee (INR)", callback_data="set_currency_INR"), InlineKeyboardButton("$ US Dollar (USD)", callback_data="set_currency_USD"))
    bot.send_message(message.chat.id, "Please select your display currency:", reply_markup=markup)

# ===== MAIN MESSAGE HANDLER =====
@bot.message_handler(func=lambda message: True)
def main_message_handler(message):
    text = message.text
    if text == "🔍 Search":
        msg = bot.reply_to(message, "Please enter what you want to search for:")
        bot.register_next_step_handler(msg, process_search_query)
    elif text == "📋 Menu": show_main_menu(message)
    elif text == "💳 Payment": show_payment_options(message)
    elif text == "🛍️ Shop": show_shop(message)
    elif text == "💰 Wallet": show_wallet(message)
    elif text.startswith('/'):
        bot.reply_to(message, "Unknown command. Please use the buttons or the /menu command.")
    else:
        process_search_query(message)

def process_search_query(message):
    # This function remains unchanged, you need to add its definition
    user_id = message.from_user.id
    if not user_has_active_subscription(user_id):
        bot.reply_to(message, "❌ You do not have an active subscription.\nPlease use the /shop command to purchase a plan.")
        return
    query_id = randint(0, 9999999)
    report = generate_report(message.text, query_id, user_id)
    if report is None or not report:
        bot.reply_to(message, "No results were found or the bot is not working.", parse_mode="Markdown")
        return
    markup = create_inline_keyboard(query_id, 0, len(report))
    try:
        bot.send_message(message.chat.id, report[0], parse_mode="html", reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Telegram API Error: {e}")
        bot.send_message(message.chat.id, text=report[0].replace("<b>", "").replace("</b>", ""), reply_markup=markup)

# ===== CALLBACK QUERY HANDLER =====
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call: CallbackQuery):
    global cash_reports, user_languages
    data = call.data
    
    # This section needs its full logic to work
    if data.startswith("/page "):
        pass 
    elif data.startswith("set_lang_"):
        lang_code = data.split('_')[-1]
        user_languages[call.from_user.id] = lang_code
        lang_name = "English" if lang_code == 'en' else "Русский"
        bot.answer_callback_query(call.id, f"Language set to {lang_name}")
    elif data.startswith("set_currency_"):
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
            balance_display = f"₹{(new_balance_usd * USD_TO_INR_RATE):.2f} INR" if currency == 'INR' else f"${new_balance_usd:.2f} USD"
            bot.send_message(call.message.chat.id, f"✅ Success! You have purchased the {plan} plan.\nYour new wallet balance is {balance_display}.")
        else:
            required_display = f"₹{(price_usd * USD_TO_INR_RATE):.2f}" if currency == 'INR' else f"${price_usd:.2f}"
            balance_display = f"₹{(new_balance_usd * USD_TO_INR_RATE):.2f}" if currency == 'INR' else f"${new_balance_usd:.2f}"
            bot.send_message(call.message.chat.id, f"❌ Insufficient balance.\n<b>Required:</b> {required_display}\n<b>Your Balance:</b> {balance_display}", parse_mode="html")
    elif data.startswith("pay_"):
        method = data.split('_')[1]
        if method == "upi": text = f"Please pay using UPI.\nOur UPI ID: `{UPI_ID}`\n\nThen submit your transaction ID using:\n`/submit upi <UTR_NUMBER>`"
        elif method == "paypal": text = f"Please pay using PayPal.\nOur PayPal ID: `{PAYPAL_ID}`\n\nThen submit your transaction ID using:\n`/submit paypal <TRANSACTION_ID>`"
        elif method == "capitalist": text = f"Please pay using Capitalist.\nOur Account No: `{CAPITALIST_ACC}`\n\nThen submit your Transaction ID using:\n`/submit capitalist <TRANSACTION_ID>`"
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
    elif data.startswith("menu_"):
        action = data.split('_')[1]
        if action == "subscription":
            user = get_user(call.from_user.id)
            sub_status = "Inactive"
            if user['subscription_end']:
                sub_end_date = datetime.fromisoformat(user['subscription_end'])
                if sub_end_date > datetime.now(): sub_status = f"✅ Active until {sub_end_date.strftime('%Y-%m-%d %H:%M')}"
            bot.send_message(call.message.chat.id, f"Subscription Status: {sub_status}")
        elif action == "wallet": show_wallet(call.message)
        elif action == "payment": show_payment_options(call.message)
        elif action == "shop": show_shop(call.message)
        elif action == "currency":
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(InlineKeyboardButton("₹ Indian Rupee (INR)", callback_data="set_currency_INR"), InlineKeyboardButton("$ US Dollar (USD)", callback_data="set_currency_USD"))
            bot.send_message(call.message.chat.id, "Please select your display currency:", reply_markup=markup)
        elif action == "refer":
            user = get_user(call.from_user.id)
            bot_username = bot.get_me().username
            referral_link = f"https.me/{bot_username}?start={user['referral_code']}"
            text = (f"🤝 **Refer & Earn Program**\n\n"
                    f"Share your unique referral link:\n`{referral_link}`\n\n"
                    f"When a new user joins via your link and makes their first purchase, you get a **{REFERRAL_BONUS_PERCENT*100:.0f}% bonus**!")
            bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

# ===== START THE BOT =====
if __name__ == "__main__":
    setup_database()
    print("Bot is starting with all features...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"An error occurred: {e}")