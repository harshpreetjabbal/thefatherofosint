# ===== COMPLETE AND FINAL CODE WITH ALL FEATURES =====
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
api_token = "8012849407:uXByp3Cn"
limit = 300
UPI_ID = "9540730341@jio"  # <-- आपकी अपडेटेड UPI ID
DB_FILE = "bot_database.db"
url = "https://leakosintapi.com/"

# करेंसी कनवर्ट करने के लिए रेट
USD_TO_INR_RATE = 83.50

# प्लान की कीमतें USD में
PLAN_PRICES_USD = {
    "daily": 0.50,
    "weekly": 2.00,
    "monthly": 3.00
}

# ===== डेटाबेस सेटअप =====
def setup_database():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance_usd REAL DEFAULT 0.0,
            subscription_end TEXT,
            currency TEXT DEFAULT 'INR'
        )
    ''')
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'currency' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN currency TEXT DEFAULT 'INR'")
    conn.commit()
    conn.close()

# ===== डेटाबेस के हेल्पर फंक्शन्स =====
def get_user(user_id):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
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
    user = get_user(user_id)
    current_balance_usd = user['balance_usd']
    if current_balance_usd < price_usd:
        return False, current_balance_usd
    new_balance_usd = current_balance_usd - price_usd
    now = datetime.now()
    if plan_type == "daily": end_date = now + timedelta(days=1)
    elif plan_type == "weekly": end_date = now + timedelta(weeks=1)
    elif plan_type == "monthly": end_date = now + timedelta(days=30)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance_usd = ?, subscription_end = ? WHERE user_id = ?", (new_balance_usd, end_date.isoformat(), user_id))
    conn.commit()
    conn.close()
    return True, new_balance_usd

def set_user_currency(user_id, currency):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET currency = ? WHERE user_id = ?", (currency, user_id))
    conn.commit()
    conn.close()

# ===== एक्सेस कण्ट्रोल फंक्शन =====
def user_has_active_subscription(user_id):
    if user_id == ADMIN_USER_ID:
        return True
    user = get_user(user_id)
    sub_end_str = user['subscription_end']
    if sub_end_str:
        sub_end_date = datetime.fromisoformat(sub_end_str)
        if sub_end_date > datetime.now():
            return True
    return False

# ===== रिपोर्ट और कीबोर्ड फंक्शन्स =====
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

# ===== बॉट कमांड्स =====
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
        get_user(user_id_to_approve)
        update_wallet(user_id_to_approve, amount_usd_to_add)
        user_after_update = get_user(user_id_to_approve)
        new_balance_usd = user_after_update['balance_usd']
        user_currency = user_after_update['currency']
        bot.reply_to(message, f"✅ Success! ${amount_usd_to_add:.2f} USD added to user {user_id_to_approve}'s wallet.")
        if user_currency == 'INR':
            credited_amount_display = f"₹{(amount_usd_to_add * USD_TO_INR_RATE):.2f} INR"
            new_balance_display = f"₹{(new_balance_usd * USD_TO_INR_RATE):.2f} INR"
        else:
            credited_amount_display = f"${amount_usd_to_add:.2f} USD"
            new_balance_display = f"${new_balance_usd:.2f} USD"
        bot.send_message(user_id_to_approve, f"🎉 Your wallet has been credited with {credited_amount_display}.\nYour new balance is {new_balance_display}.")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Incorrect format. Use: /approve <user_id> <amount_in_USD>")

@bot.message_handler(commands=['submit_utr'])
def submit_utr(message):
    try:
        utr_number = message.text.split()[1]
        user_id = message.from_user.id
        user_name = message.from_user.first_name
        approval_message = (f"❗️ New UTR Submission\n\n"
                            f"<b>User:</b> {user_name}\n"
                            f"<b>User ID:</b> <code>{user_id}</code>\n"
                            f"<b>UTR No:</b> <code>{utr_number}</code>\n\n"
                            f"To approve, reply with:\n"
                            f"<code>/approve {user_id} AMOUNT_IN_USD</code>")
        bot.send_message(ADMIN_USER_ID, approval_message, parse_mode="html")
        bot.reply_to(message, "✅ Thank you! Your UTR has been submitted. The admin will review it and credit the amount to your wallet.")
    except IndexError:
        bot.reply_to(message, "❌ Incorrect format. Use: `/submit_utr 123456789012`", parse_mode="Markdown")

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

@bot.message_handler(commands=['payment'])
def show_payment(message):
    payment_text = (f"आप UPI का उपयोग करके पेमेंट कर सकते हैं।\n\n"
                    f"हमारी UPI ID है: `{UPI_ID}`\n\n"
                    f"पेमेंट करने के बाद, अपना UTR (Transaction ID) नंबर सबमिट करने के लिए इस कमांड का उपयोग करें:\n"
                    f"`/submit_utr 123456789012`\n\n"
                    f"(123456789012 की जगह अपना असली UTR नंबर डालें)")
    bot.send_message(message.chat.id, payment_text, parse_mode="Markdown")

@bot.message_handler(commands=['language'])
def select_language(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en"),
        InlineKeyboardButton("Русский 🇷🇺", callback_data="set_lang_ru")
    )
    bot.send_message(message.chat.id, "Please select your preferred language:", reply_markup=markup)

@bot.message_handler(commands=["start"])
def send_welcome(message):
    get_user(message.from_user.id)
    bot.reply_to(message, "Hello! I am a Telegram bot that can search databases.\n\nUse /wallet to check your balance and /shop to purchase a plan.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def echo_message(message):
    if message.text.startswith('/'): return
    user_id = message.from_user.id
    if not user_has_active_subscription(user_id):
        bot.reply_to(message, "❌ You do not have an active subscription.\nPlease use the /shop command to purchase a plan.")
        return
    query_id = randint(0, 9999999)
    report = generate_report(message.text, query_id, user_id)
    if report is None or not report:
        bot.reply_to(message, "No results found or the bot is not working.", parse_mode="Markdown")
        return
    markup = create_inline_keyboard(query_id, 0, len(report))
    try:
        bot.send_message(message.chat.id, report[0], parse_mode="html", reply_markup=markup)
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Telegram API Error: {e}")
        bot.send_message(message.chat.id, text=report[0].replace("<b>", "").replace("</b>", ""), reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call: CallbackQuery):
    global cash_reports, user_languages
    data = call.data
    if data.startswith("/page "):
        query_id, page_id_str = call.data.split(" ")[1:]
        page_id = int(page_id_str)
        if query_id not in cash_reports:
            bot.answer_callback_query(call.id, "Request expired.", show_alert=True)
        else:
            report = cash_reports[query_id]
            markup = create_inline_keyboard(query_id, page_id, len(report))
            current_page_index = page_id if 0 <= page_id < len(report) else 0
            try:
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=report[current_page_index], parse_mode="html", reply_markup=markup)
            except telebot.apihelper.ApiTelegramException as e:
                if 'message is not modified' not in str(e): print(f"Error updating message: {e}")
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

# ===== बॉट को शुरू करें =====
if __name__ == "__main__":
    setup_database()
    print("Bot is starting with Database and Subscription System...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"An error occurred: {e}")