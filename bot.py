# ===================== AYARLAR =====================
import os, json, time, threading, requests
import telebot
import tweepy
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

API_TOKEN = os.getenv("API_TOKEN")

TW_API_KEY = os.getenv("TW_API_KEY")
TW_API_SECRET = os.getenv("TW_API_SECRET")
TW_ACCESS_TOKEN = os.getenv("TW_ACCESS_TOKEN")
TW_ACCESS_SECRET = os.getenv("TW_ACCESS_SECRET")

ADMIN_IDS = [7521014323, 8334707563]
ADMIN_NAMES = {
    7521014323: "BLOCK",
    8334707563: "BURAK"
}

CHECK_INTERVAL = 10
DATA_FILE = "data.json"
# ==================================================

# ===================== TELEGRAM =====================
bot = telebot.TeleBot(API_TOKEN)
USER_STATE = {}

# ===================== TWITTER =====================
twitter = tweepy.Client(
    consumer_key=TW_API_KEY,
    consumer_secret=TW_API_SECRET,
    access_token=TW_ACCESS_TOKEN,
    access_token_secret=TW_ACCESS_SECRET
)

def tweet(text):
    twitter.create_tweet(text=text)

# ===================== DATA =====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"signals": {}}

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

DATA = load_data()

# ===================== PRICE =====================
def get_price(symbol):
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/ticker/price",
            params={"symbol": symbol},
            timeout=5
        )
        return float(r.json()["price"])
    except:
        return None

# ===================== MENU =====================
def main_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Yeni Sinyal", callback_data="new"))
    return kb

@bot.message_handler(commands=["start", "menu"])
def menu(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    bot.send_message(m.chat.id, "🎛 Yönetim Paneli", reply_markup=main_menu())

# ===================== CALLBACK =====================
@bot.callback_query_handler(func=lambda c: c.data == "new")
def new_signal(c):
    USER_STATE[c.from_user.id] = {"step": "side"}
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("📈 LONG", callback_data="buy"),
        InlineKeyboardButton("📉 SHORT", callback_data="sell")
    )
    bot.edit_message_text(
        "1️⃣ İşlem yönü:",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data in ["buy", "sell"])
def set_side(c):
    USER_STATE[c.from_user.id]["side"] = c.data
    USER_STATE[c.from_user.id]["step"] = "symbol"
    bot.send_message(c.message.chat.id, "2️⃣ Parite (BTC / ETH)")

# ===================== STEPS =====================
@bot.message_handler(func=lambda m: m.from_user.id in USER_STATE)
def steps(m):
    uid = m.from_user.id
    st = USER_STATE[uid]

    if st["step"] == "symbol":
        sym = m.text.upper().replace("/", "")
        if not sym.endswith("USDT"):
            sym += "USDT"

        if get_price(sym):
            st["symbol"] = sym
            st["step"] = "entry"
            bot.send_message(m.chat.id, "3️⃣ Giriş fiyatı?")
        else:
            bot.send_message(m.chat.id, "❌ Parite bulunamadı.")

    elif st["step"] == "entry":
        st["entry"] = float(m.text)
        st["step"] = "stop"
        bot.send_message(m.chat.id, "4️⃣ Stop fiyatı?")

    elif st["step"] == "stop":
        entry = st["entry"]
        stop = float(m.text)
        side = st["side"]

        risk = abs(entry - stop)
        tp = round(entry + risk if side == "buy" else entry - risk, 5)

        sid = str(int(time.time()))

        DATA["signals"][sid] = {
            "symbol": st["symbol"],
            "side": side,
            "entry": entry,
            "stop": stop,
            "tp": tp,
            "open": True
        }
        save_data(DATA)

        tweet(
            f"🚨 YENİ İŞLEM\n\n"
            f"{st['symbol']}\n"
            f"{'LONG 📈' if side=='buy' else 'SHORT 📉'}\n\n"
            f"Giriş: {entry}\n"
            f"Stop: {stop}\n"
            f"TP: {tp}\n\n"
            f"#crypto #trading"
        )

        USER_STATE.pop(uid)
        bot.send_message(m.chat.id, "🚀 Sinyal gönderildi!", reply_markup=main_menu())

# ===================== TRACKER =====================
def tracker():
    while True:
        try:
            for s in DATA["signals"].values():
                if not s["open"]:
                    continue

                p = get_price(s["symbol"])
                if p is None:
                    continue

                if (s["side"] == "buy" and p >= s["tp"]) or \
                   (s["side"] == "sell" and p <= s["tp"]):

                    s["open"] = False
                    save_data(DATA)

                    tweet(
                        f"🎯 TP GELDİ!\n\n"
                        f"{s['symbol']}\n"
                        f"{'LONG 📈' if s['side']=='buy' else 'SHORT 📉'}\n\n"
                        f"+1R ✅"
                    )

                elif (s["side"] == "buy" and p <= s["stop"]) or \
                     (s["side"] == "sell" and p >= s["stop"]):

                    s["open"] = False
                    save_data(DATA)

                    tweet(
                        f"🛑 STOP OLDU\n\n"
                        f"{s['symbol']}\n"
                        f"{'LONG 📈' if s['side']=='buy' else 'SHORT 📉'}\n\n"
                        f"-1R ❌"
                    )

        except Exception as e:
            print("TRACKER ERROR:", e)

        time.sleep(CHECK_INTERVAL)

# ===================== START =====================
if __name__ == "__main__":
    threading.Thread(target=tracker, daemon=True).start()
    print("Bot çalışıyor")
    bot.infinity_polling(skip_pending=True)