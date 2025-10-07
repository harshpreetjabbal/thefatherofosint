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
ADMIN_USER_ID = 7631831168  # <<<--- Replace with your actual Telegram User ID
bot_token = "8202732453:AAHQBZjGwfq4OzwaaaHYWX-55HWfOFrWR1o" # Replace with your bot token
api_token = "8012849407:uXByp3Cn" # Replace with your Leakosint API token
limit = 300
UPI_ID = "9540730341@jio"
DB_FILE = "bot_database.db"
url = "https://leakosintapi.com/"
SUPPORT_USERNAME = "harshpreetjabbal"

USD_TO_INR_RATE = 83.50
PLAN_PRICES_USD = { "daily": 0.50, "weekly": 2.00, "monthly": 3.00 }

# ===== DATABASE SETUP =====
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

# ===== DATABASE HELPER FUNCTIONS =====
def get_user(user_id):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        free_trial_end_date = (datetime.now() + timedelta(days=7)).isoformat()
        cursor.execute("INSERT INTO users (user_id, subscription_end) VALUES (?, ?)", (user_id, free_trial_end_date))
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
    elif plan_type == "weekly": end_date = now + timedelta(weeks=7)
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

# ===== ACCESS CONTROL FUNCTION =====
def user_has_active_subscription(user_id):
    if user_id == ADMIN_USER_ID: return True
    user = get_user(user_id)
    if not user['subscription_end']: return False
    sub_end_date = datetime.fromisoformat(user['subscription_end'])
    return sub_end_date > datetime.now()

# ===== REPORT & KEYBOARD FUNCTIONS =====
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

# ===== MAIN MENU KEYBOARD =====
main_menu_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu_keyboard.row(KeyboardButton("🔍 Search"), KeyboardButton("📋 Menu"))
main_menu_keyboard.row(KeyboardButton("💳 Payment"), KeyboardButton("🛍️ Shop"), KeyboardButton("💰 Wallet"))

# ===== BOT COMMAND HANDLERS =====

@bot.message_handler(commands=["start"])
def send_welcome(message):
    get_user(message.from_user.id)
    welcome_text = "Hello! I am a Telegram bot that can search databases."
    bot.reply_to(message, welcome_text, reply_markup=main_menu_keyboard)

@bot.message_handler(commands=['menu'])
def show_main_menu(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("🗓️ Subscription Validity", callback_data="menu_subscription"),
        InlineKeyboardButton("💰 Wallet Balance", callback_data="menu_wallet"),
        InlineKeyboardButton("💳 Payment Options", callback_data="menu_payment"),
        InlineKeyboardButton("🛍️ Shop", callback_data="menu_shop"),
        InlineKeyboardButton("💱 Change Currency", callback_data="menu_currency"),
        InlineKeyboardButton("🛠️ Technical Support", url=f"https://t.me/{SUPPORT_USERNAME}")
    )
    bot.send_message(message.chat.id, "Here is the main menu:", reply_markup=markup)

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
        plan_name = f"▫️ {plan.capitalize()} Plan - {price_display}"
        markup.add(InlineKeyboardButton(plan_name, callback_data=f"shop_{plan}"))
    bot.send_message(message.chat.id, "Welcome to the Shop! Purchase a plan using your wallet balance:", reply_markup=markup)

@bot.message_handler(commands=['payment'])
def show_payment(message):
    payment_text = (f"You can make payments using UPI.\n\n"
                    f"Our UPI ID is: `{UPI_ID}`\n\n"
                    f"After payment, use this command to submit your UTR (Transaction ID):\n"
                    f"`/submit_utr 123456789012`\n\n"
                    f"(Replace 123456789012 with your actual UTR number)")
    bot.send_message(message.chat.id, payment_text, parse_mode="Markdown")

@bot.message_handler(commands=['export_data'])
def export_data_command(message):
    if message.from_user.id != ADMIN_USER_ID:
        bot.reply_to(message, "❌ This is an admin-only command.")
        return
    bot.reply_to(message, "⏳ Generating user data report... Please wait.")
    excel_filename = f"user_data_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        df = pd.read_sql_query("SELECT * FROM users", conn)
        conn.close()
        df.to_excel(excel_filename, index=False)
        with open(excel_filename, 'rb') as doc:
            bot.send_document(ADMIN_USER_ID, doc, caption="Here is the user data report.")
    except Exception as e:
        print(f"Error exporting data: {e}")
        bot.send_message(ADMIN_USER_ID, f"An error occurred while generating the report: {e}")
    finally:
        if os.path.exists(excel_filename):
            os.remove(excel_filename)

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

@bot.message_handler(commands=['language'])
def select_language(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en"),
        InlineKeyboardButton("Русский 🇷🇺", callback_data="set_lang_ru")
    )
    bot.send_message(message.chat.id, "Please select your preferred search result language:", reply_markup=markup)

@bot.message_handler(commands=['currency'])
def change_currency(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("₹ Indian Rupee (INR)", callback_data="set_currency_INR"),
        InlineKeyboardButton("$ US Dollar (USD)", callback_data="set_currency_USD")
    )
    bot.send_message(message.chat.id, "Please select your display currency:", reply_markup=markup)

# ===== MAIN MESSAGE HANDLER =====
@bot.message_handler(func=lambda message: True)
def main_message_handler(message):
    user_id = message.from_user.id
    text = message.text
    # Handle Reply Keyboard button presses
    if text == "🔍 Search":
        msg = bot.reply_to(message, "Please enter what you want to search for:")
        bot.register_next_step_handler(msg, process_search_query)
    elif text == "📋 Menu":
        show_main_menu(message)
    elif text == "💳 Payment":
        show_payment(message)
    elif text == "🛍️ Shop":
        show_shop(message)
    elif text == "💰 Wallet":
        show_wallet(message)
    elif text.startswith('/'):
        bot.reply_to(message, "Unknown command. Please use the buttons or the /menu command.")
    else:
        # If user types something random, assume it's a search
        process_search_query(message)

def process_search_query(message):
    user_id = message.from_user.id
    if not user_has_active_subscription(user_id):
        bot.reply_to(message, "❌ You do not have an active subscription.\nPlease use the /shop command to purchase a plan.")
        return
    query_id = randint(0, 9999999)
    report = generate_report(message.text, query_id, user_id)
    if report is None or not report:
        bot.reply_to(message, "No results were found or the bot is not working at the moment.", parse_mode="Markdown")
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
    if data.startswith("/page "):
        # Logic for paginating through search results
        query_id, page_id_str = data.split(" ")[1:]
        page_id = int(page_id_str)
        if query_id not in cash_reports:
            bot.answer_callback_query(call.id, "Request expired.", show_alert=True)
        else:
            report = cash_reports[query_id]
            markup = create_inline_keyboard(query_id, page_id, len(report))
            current_page_index = page_id % len(report)
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
            if currency == 'INR': new_balance_display = f"₹{(new_balance_usd * USD_TO_INR_RATE):.2f} INR"
            else: new_balance_display = f"${new_balance_usd:.2f} USD"
            bot.send_message(call.message.chat.id, f"✅ Success! You have purchased the {plan} plan.\nYour new wallet balance is {new_balance_display}.")
        else:
            if currency == 'INR':
                required_display = f"₹{(price_usd * USD_TO_INR_RATE):.2f}"
                balance_display = f"₹{(new_balance_usd * USD_TO_INR_RATE):.2f}"
            else:
                required_display = f"${price_usd:.2f}"
                balance_display = f"${new_balance_usd:.2f}"
            bot.send_message(call.message.chat.id, f"❌ Insufficient balance.\n<b>Required:</b> {required_display}\n<b>Your Balance:</b> {balance_display}", parse_mode="html")
    # Handle menu callbacks
    elif data == "menu_subscription":
        user = get_user(call.from_user.id)
        sub_status = "Inactive"
        if user['subscription_end']:
            sub_end_date = datetime.fromisoformat(user['subscription_end'])
            if sub_end_date > datetime.now(): sub_status = f"✅ Active until {sub_end_date.strftime('%Y-%m-%d %H:%M')}"
        bot.send_message(call.message.chat.id, f"Subscription Status: {sub_status}")
    elif data == "menu_wallet": show_wallet(call.message)
    elif data == "menu_payment": show_payment(call.message)
    elif data == "menu_shop": show_shop(call.message)
    elif data == "menu_currency": change_currency(call.message)

# ===== START THE BOT =====
if __name__ == "__main__":
    setup_database()
    print("Bot is starting with all features...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"An error occurred: {e}")