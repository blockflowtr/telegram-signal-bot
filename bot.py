# ===================== AYARLAR =====================
import os
API_TOKEN = os.getenv("API_TOKEN")  # Railway Variables

ADMIN_IDS = [7521014323, 8334707563]
ADMIN_NAMES = {
    7521014323: "BLOCK",
    8334707563: "BURAK"
}

GROUP_CHAT_ID = "@blockflowtr"
PUBLIC_TOPIC_ID = 1002

DATA_FILE = "data.json"
# ==================================================

import telebot, json, time
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

# ===================== MENÜ =====================
def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Yeni Sinyal", callback_data="btn_new"),
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

# ===================== YÖN =====================
@bot.callback_query_handler(func=lambda c: c.data.startswith("set_"))
def set_side(c):
    USER_STATE[c.from_user.id]["side"] = "buy" if "buy" in c.data else "sell"
    USER_STATE[c.from_user.id]["step"] = "symbol"
    bot.edit_message_text(
        "2️⃣ *Parite (BTC / ETH / SOL)*",
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

        st["symbol"] = sym
        st["step"] = "entry"
        bot.send_message(m.chat.id, "3️⃣ *Giriş Fiyatı?*")

    elif st["step"] == "entry":
        try:
            st["entry"] = float(m.text)
        except:
            bot.send_message(m.chat.id, "❌ Sayı gir.")
            return

        st["step"] = "stop"
        bot.send_message(m.chat.id, "4️⃣ *Stop Fiyatı?*")

    elif st["step"] == "stop":
        try:
            entry = st["entry"]
            stop = float(m.text)
            side = st["side"]
        except:
            bot.send_message(m.chat.id, "❌ Sayı gir.")
            return

        risk = abs(entry - stop)
        tp1 = round(entry + risk if side == "buy" else entry - risk, 5)
        tp2 = round(entry + 2 * risk if side == "buy" else entry - 2 * risk, 5)

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

        DATA["signals"][str(int(time.time()))] = {
            "symbol": st["symbol"],
            "side": side,
            "entry": entry,
            "stop": stop,
            "tp1": tp1,
            "tp2": tp2,
            "open": True,
            "msg_id": msg.message_id,
            "admin_id": uid
        }

        save_data(DATA)
        USER_STATE.pop(uid)
        bot.send_message(m.chat.id, "🚀 *Sinyal Gönderildi!*", parse_mode="Markdown", reply_markup=main_menu())

# ===================== START =====================
if __name__ == "__main__":
    print("Bot hazır (takipsiz sinyal modu)")
    bot.infinity_polling(skip_pending=True, timeout=60)