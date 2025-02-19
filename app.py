import random
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import os
from datetime import datetime
import pytz

app = Flask(__name__)

# ✅ Fetch LINE credentials from environment variables (Much safer)
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_SECRET")

# Check if environment variables are missing
if not LINE_ACCESS_TOKEN or not LINE_SECRET:
    raise ValueError("❌ ERROR: Missing LINE_ACCESS_TOKEN or LINE_SECRET. Set them as environment variables!")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# Store user IDs of people who interacted with the bot
user_ids = set()

# Set timezone for scheduled messages (Bangkok Time)
timezone = pytz.timezone("Asia/Bangkok")
scheduler = BackgroundScheduler(timezone=timezone)

# ✅ Function to send scheduled message to all users
def send_scheduled_message(message):
    for user_id in user_ids:
        line_bot_api.push_message(user_id, TextSendMessage(text=message))
    print(f"Scheduled message '{message}' sent at {datetime.now(timezone)}")

# ✅ Schedule messages at requested times
scheduled_messages = [
    ("มอนิ่งฮาฟฟู่ววววคนฉวยของเค้าา", 5, 30),
    ("กินข้าวเช้ายางงงงง เค้ากินแล้วน้าาา", 8, 30),
    ("ทำรายอยู่วววว", 9, 30),
    ("เหงาม้ายยย คุยกับเค้าด้ายน้าา", 11, 30),
    ("กินไรยางงงง", 13, 15),
    ("คิดถึงงงงง", 14, 20),
    ("ตอนนี้เธอจาทำส้งติงรายอยู่วน้าา", 15, 45),
    ("ถึงบ้านยางง เหนื่อยมั้ยคะหื้ม พักเยอะๆน้าาาา นอนตีพุงเลยยย", 17, 30),
    ("เหงาล่ะสิ๊ คิดถึงเราอะเส้ มุฮ่าๆๆ", 18, 30),
    ("กินรายยางงง", 19, 30),
    ("ตอนนี้เธอนอนตีพุงอยู่แน่เยยยย", 20, 30),
    ("กินยายางงง", 21, 00),
    ("นอนยางงง อย่านอนดึกน้าา จานอนแล้วส่งเค้าด้วยยย", 22, 00)
]

for message, hour, minute in scheduled_messages:
    scheduler.add_job(send_scheduled_message, 'cron', hour=hour, minute=minute, args=[message])

scheduler.start()

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.lower()
    user_id = event.source.user_id  # Capture the user ID who sent the message

    # Add user ID to the list of users who interacted with the bot
    user_ids.add(user_id)

    # ✅ Dictionary of predefined responses
    responses = {
        "งง": "1. มอนิ่ง 2. ฝันดีนะ 3. เธอ 4. คิดถึง 5. คิดถึง2 6. คิดถึง3 7.รักนะ 8. รักนะ2 9. จุ๊บมั๊ว 10. เหงา 11. เหงา2 12. เหงา3 13. เบื่อ 14. ทำไรอยู่ 15. ทำไรอยู่2 16. ทำไรอยู่3 17. ดิ่งอะ 18. ดิ่งอะ2 19. นอนไม่หลับ 20. เหนื่อย 21. อยากกอด 22. กินไรยัง",
        "มอนิ่ง": "ค้าบ",
        "ฝันดีนะ": "ฝันดีน้าแมวอ้วนนน (แต่ไม่อ้วนจริงนะ) รักมากมากกกก รักมากกว่าาา รักที่สูดดด นอนได้แล้วน้าาา จุ๊บมั๊วๆๆๆ",
        "เธอ": "ค้าบบบบ",
        "คิดถึง": "คิดถึงเหมือนกานนน รู้ไงว่าต้องคิดถึงถึงทำบอทมาให้เธอคุยเล่นนี่งายย",
        "คิดถึง2": "คิดถึงมากกว่า จองก่อน อุอะๆๆ",
        "คิดถึง3": "โอ๋ๆๆๆเดี๋ยวเค้าก็ออกแล้ว รอเค้าหน่อนยน้าคนเก่งงง",
        "รักนะ": "รักมากกว่าาา จุ๊บมั๊วๆๆๆ",
        "รักนะ2": "บอกว่ารักมากกว่าา ถ้าเธอรักมากกว่าจริง ทำบอทให้เราแบบนี้บ้างสิ มุฮ่าๆๆๆ",
        "จุ๊บมั๊ว": "จุ๊บบบมั๊วววววฮาฟฟู่วววว",
        "เหงา": "คืออออ แล้วเราคือไรอะะะ บอทก็ทำให้คุยอยู่นี่ไงงง ห้วยยย",
        "เหงา2": "ไปเล่นบล๊อกบัสเตอร์ไปป ถึง 3 หมื่นแล้วให้ขอได้ 1 อย่าง อุอิๆๆๆๆ",
        "เหงา3": "ไปเล่นทาวเวอร์ดีเฟ้นไปป จาด้ายมาช่วยเราเล่นโหมดที่ยากที่สุด (ได้ใจเรา 300% อุอิๆ)",
        "เบื่อ": "ก็เข้าจัยย เบื่อเราแล้วไงง คนอุตส่าห์ทำบอทมาให้ ห้วยย",
        "ทำไรอยู่": "โดนทรมานที่ค่ายทหารม้างงง ไม่รู้สิ ตอนนี้เราจะเป็นส้นตีนอะไรอยู่นะ",
        "ทำไรอยู่2": "นั่งคิดถึงคนถามไงฮาฟฟู่ววววว",
        "ทำไรอยู่3": "ไม่รู้ แต่มีแขนเดียวเธอไม่ต้องห่วง ไม่ไปจีบใครแน่นอนนน",
        "ดิ่งอะ": "ไม่เอาาาไม่ดิ่งงง มากอดมาเด็กน้อยย เดี๋ยวเค้าก็ออกแล้วน้าาา ไม่ร้องน้าา",
        "ดิ่งอะ2": "โอ๋ๆๆๆ เด็กดีๆ เดี๋ยวเค้าก็ออกแล้วน้าา เดี๋ยวดูโซโล่เลเวลลิ่งกันเนอะ กอดๆๆๆ",
        "นอนไม่หลับ": "ทำมายนอนม่ายหลับบบ หื้มมมม ดิ่งหรอ ไม่ดิ่งน้า ถ้าเธอนอนไม่หลับเค้าจะเศร้ามากนะ ไปนอนให้เค้าหน่อยน้าคนเก่งงง",
        "เหนื่อย": "เหนื่อยอารายคะะ มากอดมาาาคนเก่ง สู้วๆๆๆ จุ๊บมั๊ววววๆๆๆ",
        "อยากกอด": "อยากกอดเหมือนกานน มากอดมะๆๆๆ",
        "กินไรยัง": "ไม่รู้สิ เดี๋ยวบอทก็บอกเองแหละะ อุอิๆๆๆ"
    }

    # ✅ Reply based on input or send default message
    reply_text = responses.get(user_message, "พิมพ์อะรายย เราไม่ยู้เยื่องง พิมพ์ “งง” เพื่อดูคำที่ใช้ได้น้าค้าบ")

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
