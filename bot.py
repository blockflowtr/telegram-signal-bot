# ===================== AYARLAR =====================
import os, json, time, threading, requests
import telebot
import tweepy
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

# Çevre Değişkenleri
API_TOKEN = os.getenv("API_TOKEN")
TW_API_KEY = os.getenv("TW_API_KEY")
TW_API_SECRET = os.getenv("TW_API_SECRET")
TW_ACCESS_TOKEN = os.getenv("TW_ACCESS_TOKEN")
TW_ACCESS_SECRET = os.getenv("TW_ACCESS_SECRET")

ADMIN_IDS = [7521014323, 8334707563]
CHECK_INTERVAL = 10
DATA_FILE = "data.json"
# ==================================================

# ===================== BAĞLANTILAR =====================
bot = telebot.TeleBot(API_TOKEN)
USER_STATE = {}

# Twitter v2 Bağlantısı
twitter = tweepy.Client(
    consumer_key=TW_API_KEY,
    consumer_secret=TW_API_SECRET,
    access_token=TW_ACCESS_TOKEN,
    access_token_secret=TW_ACCESS_SECRET
)

def tweet(text):
    try:
        twitter.create_tweet(text=text)
    except Exception as e:
        print(f"TWEET ERROR: {e}")

# ===================== VERİ YÖNETİMİ =====================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"signals": {}}
    return {"signals": {}}

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

DATA = load_data()

# ===================== FİYAT ÇEKME =====================
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

# ===================== TELEGRAM MENÜ =====================
def main_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Yeni Sinyal", callback_data="new"))
    return kb

@bot.message_handler(commands=["start", "menu"])
def menu(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    bot.send_message(m.chat.id, "🎛 Yönetim Paneli", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "new")
def new_signal(c):
    USER_STATE[c.from_user.id] = {"step": "side"}
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("📈 LONG", callback_data="buy"),
        InlineKeyboardButton("📉 SHORT", callback_data="sell")
    )
    bot.edit_message_text("1️⃣ İşlem yönü:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["buy", "sell"])
def set_side(c):
    USER_STATE[c.from_user.id]["side"] = c.data
    USER_STATE[c.from_user.id]["step"] = "symbol"
    bot.send_message(c.message.chat.id, "2️⃣ Parite (Örn: BTC veya ETH)")

@bot.message_handler(func=lambda m: m.from_user.id in USER_STATE)
def steps(m):
    uid = m.from_user.id
    st = USER_STATE[uid]

    if st["step"] == "symbol":
        sym = m.text.upper().replace("/", "")
        if not sym.endswith("USDT"): sym += "USDT"

        if get_price(sym):
            st["symbol"] = sym
            st["step"] = "entry"
            bot.send_message(m.chat.id, "3️⃣ Giriş fiyatı?")
        else:
            bot.send_message(m.chat.id, "❌ Parite bulunamadı.")

    elif st["step"] == "entry":
        try:
            st["entry"] = float(m.text)
            st["step"] = "stop"
            bot.send_message(m.chat.id, "4️⃣ Stop fiyatı?")
        except: bot.send_message(m.chat.id, "❌ Lütfen sayısal bir değer girin.")

    elif st["step"] == "stop":
        try:
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

            tweet(f"🚨 YENİ İŞLEM\n\n{st['symbol']}\n{'LONG 📈' if side=='buy' else 'SHORT 📉'}\n\n"
                  f"Giriş: {entry}\nStop: {stop}\nTP: {tp}\n\n#crypto #trading")

            USER_STATE.pop(uid)
            bot.send_message(m.chat.id, "🚀 Sinyal gönderildi!", reply_markup=main_menu())
        except: bot.send_message(m.chat.id, "❌ Hatalı değer.")

# ===================== TAKİP SİSTEMİ (DÜZELTİLDİ) =====================
def tracker():
    while True:
        try:
            # list() kullanarak döngü sırasında veri eklenirse hata almayı engelliyoruz
            for sid, s in list(DATA["signals"].items()):
                if not s.get("open") or "tp" not in s:
                    continue

                current_price = get_price(s["symbol"])
                if current_price is None:
                    continue

                # Kar Al (TP) Kontrolü
                is_tp = (s["side"] == "buy" and current_price >= s["tp"]) or \
                        (s["side"] == "sell" and current_price <= s["tp"])
                
                # Zarar Kes (Stop) Kontrolü
                is_stop = (s["side"] == "buy" and current_price <= s["stop"]) or \
                          (s["side"] == "sell" and current_price >= s["stop"])

                if is_tp:
                    DATA["signals"][sid]["open"] = False
                    save_data(DATA)
                    tweet(f"🎯 TP GELDİ!\n\n{s['symbol']}\n{'LONG 📈' if s['side']=='buy' else 'SHORT 📉'}\n\n+1R ✅")
                
                elif is_stop:
                    DATA["signals"][sid]["open"] = False
                    save_data(DATA)
                    tweet(f"🛑 STOP OLDU\n\n{s['symbol']}\n{'LONG 📈' if s['side']=='buy' else 'SHORT 📉'}\n\n-1R ❌")

        except Exception as e:
            print(f"TRACKER ERROR: {e}")

        time.sleep(CHECK_INTERVAL)

# ===================== BAŞLATMA =====================
if __name__ == "__main__":
    threading.Thread(target=tracker, daemon=True).start()
    print("Bot aktif ve takip başlıyor...")
    bot.infinity_polling(skip_pending=True)