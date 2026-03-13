import os
import telebot
import requests
import json
import time
import threading
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

API_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_ID")
PUBLIC_TOPIC_ID = int(os.getenv("TOPIC_ID", "0"))

CHECK_INTERVAL = 10
DATA_FILE = "data.json"

bot = telebot.TeleBot(API_TOKEN)
USER_STATE = {}

# ===================== VERİ =====================

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE,"r",encoding="utf-8") as f:
            return json.load(f)
    return {
        "signals":{},
        "stats":{
            "tp1":0,
            "tp2":0,
            "loss":0
        }
    }

def save_data(d):
    with open(DATA_FILE,"w",encoding="utf-8") as f:
        json.dump(d,f,indent=2,ensure_ascii=False)

DATA = load_data()

# ===================== FİYAT =====================

def get_price(symbol):
    try:
        r = requests.get(
            f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",
            timeout=5
        )
        return float(r.json()["price"])
    except:
        return None

# ===================== WINRATE =====================

def winrate():
    s = DATA["stats"]
    total = s["tp2"] + s["loss"]
    if total == 0:
        return 0
    return round((s["tp2"]/total)*100,2)

# ===================== MENÜ =====================

def main_menu():

    s = DATA["stats"]

    kb = InlineKeyboardMarkup(row_width=2)

    kb.add(
        InlineKeyboardButton("➕ Yeni Sinyal",callback_data="btn_new"),
        InlineKeyboardButton("📂 Açık İşlemler",callback_data="btn_open")
    )

    kb.add(
        InlineKeyboardButton(
            f"📊 Winrate %{winrate()}",
            callback_data="btn_stats"
        )
    )

    return kb

@bot.message_handler(commands=["start","menu"])
def menu(m):

    bot.send_message(
        m.chat.id,
        "🎛 *Sinyal Yönetim Paneli*",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ===================== İSTATİSTİK =====================

@bot.callback_query_handler(func=lambda c: c.data=="btn_stats")
def stats(c):

    s = DATA["stats"]

    bot.answer_callback_query(
        c.id,
        f"📊 GENEL PERFORMANS\n\n"
        f"🎯 TP1: {s['tp1']}\n"
        f"🏆 TP2: {s['tp2']}\n"
        f"🛑 Stop: {s['loss']}\n\n"
        f"📈 Winrate: %{winrate()}",
        show_alert=True
    )

# ===================== AÇIK İŞLEMLER =====================

@bot.callback_query_handler(func=lambda c: c.data=="btn_open")
def open_trades(c):

    kb = InlineKeyboardMarkup()
    found=False

    for sid,s in DATA["signals"].items():

        if s["open"]:

            found=True

            kb.add(
                InlineKeyboardButton(
                    f"{s['symbol']} ❌",
                    callback_data=f"close_{sid}"
                )
            )

    if not found:
        bot.answer_callback_query(c.id,"Açık işlem yok.")
        return

    bot.send_message(
        c.message.chat.id,
        "📂 Açık İşlemler",
        reply_markup=kb
    )

# ===================== YENİ SİNYAL =====================

@bot.callback_query_handler(func=lambda c: c.data=="btn_new")
def new_signal(c):

    USER_STATE[c.from_user.id]={"step":"side"}

    kb=InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton("📈 LONG",callback_data="set_buy"),
        InlineKeyboardButton("📉 SHORT",callback_data="set_sell")
    )

    bot.edit_message_text(
        "1️⃣ İşlem yönü seç",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=kb
    )

# ===================== YÖN =====================

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_"))
def set_side(c):

    USER_STATE[c.from_user.id]["side"]="buy" if "buy" in c.data else "sell"
    USER_STATE[c.from_user.id]["step"]="symbol"

    bot.edit_message_text(
        "2️⃣ Parite yaz\n\nÖrnek: BTC veya ETH",
        c.message.chat.id,
        c.message.message_id
    )

# ===================== ADIMLAR =====================

@bot.message_handler(func=lambda m: m.from_user.id in USER_STATE)
def steps(m):

    uid=m.from_user.id
    st=USER_STATE[uid]

    if st["step"]=="symbol":

        sym=m.text.upper()+"USDT"

        if get_price(sym):

            st["symbol"]=sym
            st["step"]="entry"

            bot.send_message(m.chat.id,"3️⃣ Giriş fiyatı")

        else:

            bot.send_message(m.chat.id,"❌ Parite bulunamadı")

    elif st["step"]=="entry":

        st["entry"]=float(m.text)
        st["step"]="stop"

        bot.send_message(m.chat.id,"4️⃣ Stop fiyatı")

    elif st["step"]=="stop":

        entry=st["entry"]
        stop=float(m.text)
        side=st["side"]

        risk=abs(entry-stop)

        tp1=round(entry+risk if side=="buy" else entry-risk,5)
        tp2=round(entry+2*risk if side=="buy" else entry-2*risk,5)

        sid=str(int(time.time()))

        msg=bot.send_message(

            GROUP_CHAT_ID,

            f"🚨 *YENİ SİNYAL*\n\n"
            f"💎 *{st['symbol']}*\n"
            f"{'📈 LONG' if side=='buy' else '📉 SHORT'}\n\n"
            f"🎯 Giriş: `{entry}`\n"
            f"🛑 Stop: `{stop}`\n"
            f"✅ TP1: `{tp1}`\n"
            f"🏆 TP2: `{tp2}`\n\n"
            f"🕒 {datetime.now().strftime('%H:%M')}",

            parse_mode="Markdown",
            message_thread_id=PUBLIC_TOPIC_ID

        )

        DATA["signals"][sid]={

            "symbol":st["symbol"],
            "side":side,
            "entry":entry,
            "stop":stop,
            "tp1":tp1,
            "tp2":tp2,
            "tp1_hit":False,
            "open":True,
            "msg_id":msg.message_id

        }

        save_data(DATA)

        USER_STATE.pop(uid)

        bot.send_message(m.chat.id,"🚀 Sinyal gönderildi",reply_markup=main_menu())

# ===================== MANUEL KAPAT =====================

@bot.callback_query_handler(func=lambda c: c.data.startswith("close_"))
def manual_close(c):

    sid=c.data.split("_")[1]

    s=DATA["signals"].get(sid)

    if not s or not s["open"]:
        return

    price=get_price(s["symbol"])

    entry=s["entry"]
    side=s["side"]

    pnl=(price-entry)/entry*100 if side=="buy" else (entry-price)/entry*100

    pnl=round(pnl,2)

    emoji="🟢" if pnl>=0 else "🔴"

    s["open"]=False

    save_data(DATA)

    bot.send_message(

        GROUP_CHAT_ID,

        f"⚠️ *MANUEL KAPATMA*\n\n"
        f"💎 {s['symbol']}\n"
        f"{emoji} PnL: {pnl}%",

        parse_mode="Markdown",
        message_thread_id=PUBLIC_TOPIC_ID,
        reply_to_message_id=s["msg_id"]

    )

    bot.answer_callback_query(c.id,"İşlem kapatıldı")

# ===================== GÜNLÜK RAPOR =====================

@bot.message_handler(commands=["gunluk"])
def daily(m):

    s=DATA["stats"]

    msg=(

        f"📊 *GÜNLÜK PERFORMANS*\n\n"
        f"🎯 TP1: {s['tp1']}\n"
        f"🏆 TP2: {s['tp2']}\n"
        f"🛑 Stop: {s['loss']}\n\n"
        f"📈 Winrate: %{winrate()}\n\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y')}"

    )

    bot.send_message(
        GROUP_CHAT_ID,
        msg,
        parse_mode="Markdown",
        message_thread_id=PUBLIC_TOPIC_ID
    )

# ===================== TRACKER =====================

def tracker():

    while True:

        try:

            for s in DATA["signals"].values():

                if not s["open"]:
                    continue

                p=get_price(s["symbol"])

                if not p:
                    continue

                if not s["tp1_hit"]:

                    if (s["side"]=="buy" and p>=s["tp1"]) or (s["side"]=="sell" and p<=s["tp1"]):

                        s["tp1_hit"]=True
                        DATA["stats"]["tp1"]+=1

                        save_data(DATA)

                        bot.send_message(

                            GROUP_CHAT_ID,

                            "🎯 *TP1 HEDEFİNE ULAŞILDI*\n\n"
                            "💰 İlk kâr hedefi alındı\n"
                            "🔒 Kısmi kâr realizasyonu yapılabilir\n"
                            "📉 Stop giriş seviyesine çekilebilir",

                            parse_mode="Markdown",
                            message_thread_id=PUBLIC_TOPIC_ID,
                            reply_to_message_id=s["msg_id"]

                        )

                if (s["side"]=="buy" and p>=s["tp2"]) or (s["side"]=="sell" and p<=s["tp2"]):

                    s["open"]=False
                    DATA["stats"]["tp2"]+=1

                    save_data(DATA)

                    bot.send_message(

                        GROUP_CHAT_ID,

                        "🏆 *TP2 HEDEFİNE ULAŞILDI*\n\n"
                        "🚀 İşlem tam hedefe ulaştı\n"
                        "Tebrikler!",

                        parse_mode="Markdown",
                        message_thread_id=PUBLIC_TOPIC_ID,
                        reply_to_message_id=s["msg_id"]

                    )

                elif (s["side"]=="buy" and p<=s["stop"]) or (s["side"]=="sell" and p>=s["stop"]):

                    s["open"]=False
                    DATA["stats"]["loss"]+=1

                    save_data(DATA)

                    bot.send_message(

                        GROUP_CHAT_ID,

                        "🛑 *STOP TETİKLENDİ*\n\n"
                        "📉 Risk yönetimi gereği işlem kapandı\n"
                        "Bir sonraki fırsatı bekliyoruz",

                        parse_mode="Markdown",
                        message_thread_id=PUBLIC_TOPIC_ID,
                        reply_to_message_id=s["msg_id"]

                    )

        except:
            pass

        time.sleep(CHECK_INTERVAL)

# ===================== BAŞLAT =====================

if __name__=="__main__":

    threading.Thread(target=tracker,daemon=True).start()

    print("Bot başlatıldı")

    while True:

        try:
            bot.infinity_polling(timeout=60,long_polling_timeout=60)
        except:
            time.sleep(5)
