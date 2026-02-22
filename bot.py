# ===================== AYARLAR =====================
import os
API_TOKEN = os.getenv("API_TOKEN")  # 🔐 Railway ENV variable

ADMIN_IDS = [7521014323, 8334707563]
ADMIN_NAMES = {
    7521014323: "BLOCK",
    8334707563: "BURAK"
}

GROUP_CHAT_ID = "@blockflowtr"
PUBLIC_TOPIC_ID = 1002

CHECK_INTERVAL = 10
DATA_FILE = "data.json"
# ==================================================

import telebot, requests, json, time, threading
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

bot = telebot.TeleBot(API_TOKEN)
USER_STATE = {}

# ===================== VERİ =====================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "signals": {},
        "stats": {
            str(a): {"tp1": 0, "tp2": 0, "loss": 0} for a in ADMIN_IDS
        }
    }

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

DATA = load_data()

# ===================== FUTURES FİYAT =====================
def get_price(symbol):
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/ticker/price",
            params={"symbol": symbol},
            timeout=10
        )
        data = r.json()
        return float(data["price"])
    except Exception as e:
        print("FUTURES PRICE ERROR:", e)
        return None

# ===================== MENÜ =====================
def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Yeni Sinyal", callback_data="btn_new"),
        InlineKeyboardButton("📂 Açık İşlemler", callback_data="btn_open"),
        InlineKeyboardButton("📊 İstatistik", callback_data="btn_stats")
    )
    return kb

@bot.message_handler(commands=["start", "menu"])
def menu(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    bot.send_message(
        m.chat.id,
        "🎛 *Yönetim Paneli*",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ===================== CALLBACK =====================
@bot.callback_query_handler(func=lambda c: c.data.startswith("btn_"))
def callbacks(c):
    uid = c.from_user.id

    if c.data == "btn_new":
        USER_STATE[uid] = {"step": "side"}
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("📈 LONG", callback_data="set_buy"),
            InlineKeyboardButton("📉 SHORT", callback_data="set_sell")
        )
        bot.edit_message_text(
            "1️⃣ *İşlem Yönü:*",
            c.message.chat.id,
            c.message.message_id,
            parse_mode="Markdown",
            reply_markup=kb
        )

    elif c.data == "btn_stats":
        s = DATA["stats"][str(uid)]
        bot.answer_callback_query(
            c.id,
            f"📊 {ADMIN_NAMES.get(uid)}\n"
            f"🎯 TP1: {s['tp1']}\n"
            f"🏆 TP2: {s['tp2']}\n"
            f"🛑 Stop: {s['loss']}",
            show_alert=True
        )

    elif c.data == "btn_open":
        kb = InlineKeyboardMarkup()
        found = False
        for sid, s in DATA["signals"].items():
            if s["open"]:
                found = True
                kb.add(
                    InlineKeyboardButton(
                        f"{s['symbol']} ❌",
                        callback_data=f"close_{sid}"
                    )
                )
        if not found:
            bot.answer_callback_query(c.id, "Açık işlem yok.")
        else:
            bot.send_message(
                c.message.chat.id,
                "📂 *Açık İşlemler*",
                parse_mode="Markdown",
                reply_markup=kb
            )

# ===================== MANUEL KAPAT =====================
@bot.callback_query_handler(func=lambda c: c.data.startswith("close_"))
def manual_close(c):
    sid = c.data.split("_")[1]
    s = DATA["signals"].get(sid)
    if not s or not s["open"]:
        return

    price = get_price(s["symbol"])
    if not price:
        return

    entry = s["entry"]
    side = s["side"]
    pnl = (price - entry) / entry * 100 if side == "buy" else (entry - price) / entry * 100
    pnl = round(pnl, 2)
    emoji = "🟢" if pnl >= 0 else "🔴"

    s["open"] = False
    save_data(DATA)

    bot.send_message(
        GROUP_CHAT_ID,
        (
            f"⚠️ *MANUEL KAPATMA*\n\n"
            f"💎 *{s['symbol']}*\n"
            f"{'📈 LONG' if side=='buy' else '📉 SHORT'}\n\n"
            f"🎯 Giriş: `{entry}`\n"
            f"⏹ Kapanış: `{round(price,5)}`\n\n"
            f"{emoji} *PnL: {pnl}%*"
        ),
        parse_mode="Markdown",
        message_thread_id=PUBLIC_TOPIC_ID,
        reply_to_message_id=s["msg_id"]
    )

    bot.answer_callback_query(c.id, "İşlem kapatıldı.")

# ===================== YÖN =====================
@bot.callback_query_handler(func=lambda c: c.data.startswith("set_"))
def set_side(c):
    USER_STATE[c.from_user.id]["side"] = "buy" if "buy" in c.data else "sell"
    USER_STATE[c.from_user.id]["step"] = "symbol"
    bot.edit_message_text(
        "2️⃣ *Parite (BTC / ETH)*",
        c.message.chat.id,
        c.message.message_id,
        parse_mode="Markdown"
    )

# ===================== ADIMLAR =====================
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
            bot.send_message(m.chat.id, "3️⃣ *Giriş Fiyatı?*")
        else:
            bot.send_message(m.chat.id, "❌ Parite yok.")

    elif st["step"] == "entry":
        st["entry"] = float(m.text)
        st["step"] = "stop"
        bot.send_message(m.chat.id, "4️⃣ *Stop Fiyatı?*")

    elif st["step"] == "stop":
        entry = st["entry"]
        stop = float(m.text)
        side = st["side"]

        risk = abs(entry - stop)
        tp1 = round(entry + risk if side == "buy" else entry - risk, 5)
        tp2 = round(entry + 2 * risk if side == "buy" else entry - 2 * risk, 5)

        sid = str(int(time.time()))

        msg = bot.send_message(
            GROUP_CHAT_ID,
            (
                f"🚨 *YENİ SİNYAL*\n\n"
                f"💎 *{st['symbol']}*\n"
                f"{'📈 LONG' if side=='buy' else '📉 SHORT'}\n\n"
                f"🎯 Giriş: `{entry}`\n"
                f"🛑 Stop: `{stop}`\n"
                f"✅ TP1: `{tp1}`\n"
                f"🏆 TP2: `{tp2}`\n\n"
                f"🕒 {datetime.now().strftime('%H:%M')}"
            ),
            parse_mode="Markdown",
            message_thread_id=PUBLIC_TOPIC_ID
        )

        DATA["signals"][sid] = {
            "symbol": st["symbol"],
            "side": side,
            "entry": entry,
            "stop": stop,
            "tp1": tp1,
            "tp2": tp2,
            "tp1_hit": False,
            "open": True,
            "msg_id": msg.message_id,
            "admin_id": uid
        }

        save_data(DATA)
        USER_STATE.pop(uid)
        bot.send_message(m.chat.id, "🚀 Sinyal Gönderildi!", reply_markup=main_menu())

# ===================== TRACKER =====================
def tracker():
    while True:
        try:
            for s in DATA["signals"].values():
                if not s["open"]:
                    continue

                p = get_price(s["symbol"])
                if not p:
                    continue

                admin = str(s["admin_id"])

                if not s["tp1_hit"]:
                    if (s["side"] == "buy" and p >= s["tp1"]) or (s["side"] == "sell" and p <= s["tp1"]):
                        s["tp1_hit"] = True
                        DATA["stats"][admin]["tp1"] += 1
                        save_data(DATA)
                        bot.send_message(
                            GROUP_CHAT_ID,
                            "🎯 *TP1!*",
                            parse_mode="Markdown",
                            message_thread_id=PUBLIC_TOPIC_ID,
                            reply_to_message_id=s["msg_id"]
                        )

                if (s["side"] == "buy" and p >= s["tp2"]) or (s["side"] == "sell" and p <= s["tp2"]):
                    s["open"] = False
                    DATA["stats"][admin]["tp2"] += 1
                    save_data(DATA)
                    bot.send_message(
                        GROUP_CHAT_ID,
                        "🏆 *TP2!*",
                        parse_mode="Markdown",
                        message_thread_id=PUBLIC_TOPIC_ID,
                        reply_to_message_id=s["msg_id"]
                    )

                elif (s["side"] == "buy" and p <= s["stop"]) or (s["side"] == "sell" and p >= s["stop"]):
                    s["open"] = False
                    DATA["stats"][admin]["loss"] += 1
                    save_data(DATA)
                    bot.send_message(
                        GROUP_CHAT_ID,
                        "🛑 *STOP!*",
                        parse_mode="Markdown",
                        message_thread_id=PUBLIC_TOPIC_ID,
                        reply_to_message_id=s["msg_id"]
                    )
        except Exception as e:
            print("TRACKER ERROR:", e)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    threading.Thread(target=tracker, daemon=True).start()
    print("Bot hazır")
    bot.infinity_polling(skip_pending=True, timeout=60)