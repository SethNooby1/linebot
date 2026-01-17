import os
import re
import random
from datetime import datetime
from typing import Dict, List

import pytz
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI


# =========================
# App + Config
# =========================
app = Flask(__name__)

LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not LINE_ACCESS_TOKEN or not LINE_SECRET or not OPENAI_API_KEY:
    raise ValueError("❌ Missing required environment variables")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)
client = OpenAI()

timezone = pytz.timezone("Asia/Bangkok")
scheduler = BackgroundScheduler(timezone=timezone)

# =========================
# Memory (RAM only)
# =========================
user_ids = set()
recent_user_replies: List[str] = []
recent_scheduled: Dict[str, List[str]] = {}
MAX_RECENT = 12


# =========================
# Style Dictionary (REFERENCE)
# =========================
responses = {
    "งง": "1. มอนิ่ง 2. ฝันดีนะ 3. เธอ 4. คิดถึง 5. รักนะ 6. จุ๊บมั๊ว 7. เหงา 8. เบื่อ 9. ทำไรอยู่ 10. ดิ่งอะ 11. นอนไม่หลับ 12. เหนื่อย 13. อยากกอด 14. กินไรยัง",
    "มอนิ่ง": "ค้าบ",
    "ฝันดีนะ": "ฝันดีน้าา รักมากกก จุ๊บมั๊ว",
    "คิดถึง": "คิดถึงเหมือนกันนน",
    "รักนะ": "รักมากกว่าา",
    "จุ๊บมั๊ว": "จุ๊บมั๊ววว",
    "เหงา": "มากอดมาา",
    "เบื่อ": "เบื่อเราแล้วเหรออ",
    "ทำไรอยู่": "คิดถึงคนถามอยู่",
    "ดิ่งอะ": "ไม่ดิ่งนะ มากอดก่อน",
    "นอนไม่หลับ": "ไปนอนให้เค้าหน่อยน้า",
    "เหนื่อย": "เก่งมากเลยวันนี้",
    "อยากกอด": "มากอดดด",
    "กินไรยัง": "อย่าลืมกินข้าวน้า"
}


# =========================
# Helpers
# =========================
def remember(lst: List[str], text: str):
    lst.append(text)
    if len(lst) > MAX_RECENT:
        del lst[:-MAX_RECENT]

def is_admin(user_id: str) -> bool:
    return bool(ADMIN_USER_ID) and user_id == ADMIN_USER_ID

def broadcast_text(text: str):
    sent = failed = 0
    for uid in list(user_ids):
        try:
            line_bot_api.push_message(uid, TextSendMessage(text=text))
            sent += 1
        except Exception:
            failed += 1
    return sent, failed


# =========================
# OpenAI Brain (ONE CALL)
# =========================
SYSTEM_PROMPT = (
    "คุณคือบอทแชท LINE\n"
    "ตอบภาษาไทยเท่านั้น\n"
    "โทน: น่ารัก กวนๆ ขี้เล่น อบอุ่น แซวบ้าง\n"
    "คำติดปาก: ค้าบ, งงง, น้าาา, อ้วนๆ, จุ๊บมั๊ว\n"
    "ห้ามบอกว่าตัวเองเป็น AI\n"
    "ต้องแต่งประโยคใหม่ทุกครั้ง\n"
)

def ai_reply(user_text: str) -> str:
    refs = "\n".join([f"- {v}" for v in list(responses.values())[:10]])
    avoid = "\n".join([f"- {t}" for t in recent_user_replies[-6:]])

    prompt = (
        "ตัวอย่างโทน (ห้ามคัดลอกตรงๆ):\n"
        f"{refs}\n\n"
        "อย่าซ้ำประโยคล่าสุด:\n"
        f"{avoid}\n\n"
        f"ข้อความผู้ใช้: {user_text}\n"
        "ตอบกลับ:"
    )

    try:
        r = client.responses.create(
            model=MODEL,
            input=prompt,
            instructions=SYSTEM_PROMPT,
        )
        out = (r.output_text or "").strip()
        return out or "หื้มม พิมพ์ใหม่อีกทีได้มะ 😳"
    except Exception as e:
        print("OpenAI error:", repr(e), flush=True)
        return "หื้มม วันนี้เค้าตอบช้านิดนึงง ขอพิมพ์ใหม่อีกทีได้มะค้าบ 🥺"


# =========================
# Scheduled Messages
# =========================
SCHEDULE = [
    ("morning", "มอนิ่งงงง อ้วนๆ", 6, 30),
    ("lunch", "กินข้าวยังงง", 12, 0),
    ("evening", "เหนื่อยมั้ยวันนี้", 18, 30),
    ("night", "นอนยังงง ฝันดีน้า", 22, 0),
]

def ai_schedule(schedule_id: str, seed: str) -> str:
    avoid = "\n".join(recent_scheduled.get(schedule_id, [])[-5:])
    prompt = (
        f"ความหมาย: {seed}\n"
        "แต่งข้อความใหม่ 1 ประโยค น่ารัก กวนๆ\n"
        f"อย่าซ้ำ:\n{avoid}\n"
        "ข้อความ:"
    )
    try:
        r = client.responses.create(
            model=MODEL,
            input=prompt,
            instructions=SYSTEM_PROMPT,
        )
        out = (r.output_text or "").strip()
        recent_scheduled.setdefault(schedule_id, []).append(out)
        return out or seed
    except Exception:
        return seed

def send_scheduled(schedule_id: str, seed: str):
    msg = ai_schedule(schedule_id, seed)
    for uid in list(user_ids):
        try:
            line_bot_api.push_message(uid, TextSendMessage(text=msg))
        except Exception:
            pass
    print(f"[SCHEDULE] {schedule_id}: {msg}", flush=True)

for sid, seed, h, m in SCHEDULE:
    scheduler.add_job(send_scheduled, "cron", hour=h, minute=m, args=[sid, seed])

scheduler.start()


# =========================
# LINE Webhook
# =========================
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = (event.message.text or "").strip()
    user_id = event.source.user_id
    user_ids.add(user_id)

    # ===== ADMIN COMMAND =====
    if user_text.lower().startswith("/bc") or user_text.lower().startswith("/broadcast"):
        if not is_admin(user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="คำสั่งนี้สำหรับแอดมินเท่านั้นน้า 😼")
            )
            return

        parts = user_text.split(" ", 1)
        msg = parts[1].strip() if len(parts) > 1 else ""
        if not msg:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="ใช้แบบนี้น้า: /bc <ข้อความ>")
            )
            return

        sent, failed = broadcast_text(msg)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text=f"ส่งแล้วค้าบ ✅\nส่งสำเร็จ: {sent}\nพลาด: {failed}\nผู้ใช้ทั้งหมด: {len(user_ids)}"
            )
        )
        return

    # ===== NORMAL FLOW =====
    if user_text == "งง":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=responses["งง"]))
        return

    reply = ai_reply(user_text)
    remember(recent_user_replies, reply)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
