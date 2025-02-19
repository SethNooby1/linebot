import random
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
import os
from datetime import datetime
import pytz

app = Flask(__name__)

# 🚨 Use your LINE credentials directly in the code (Not recommended for production)
LINE_ACCESS_TOKEN = "RfVeptwLWL4vUHd6k24I1eFMJMa2QgyI22GuPhXQ77OEkbTRgBvwI/QX+SgnF/1gP7XjeZcij+uONTTYT7Xb45tRYweHLmbqei6AhVqoxTP8n2ci3oRaVWXaV084nBWYg5MDP6tzzMqz0LVg5bAfWAdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "84262e42120bc8acb109d4f1a0fcb17b"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# Store user IDs of people who interacted with the bot
user_ids = set()

# Set timezone for scheduled messages (Bangkok Time)
timezone = pytz.timezone("Asia/Bangkok")
scheduler = BackgroundScheduler(timezone=timezone)

# Function to send scheduled message at 10:27 AM
def send_scheduled_message():
    message = "hohohoh"
    for user_id in user_ids:
        line_bot_api.push_message(user_id, TextSendMessage(text=message))
    print(f"Scheduled message sent at {datetime.now(timezone)}")

# Schedule the message (Set it to send at 10:27 AM)
scheduler.add_job(send_scheduled_message, 'cron', hour=22, minute=39)
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

    # Respond based on user input
    if user_message == "hi":
        reply_text = "suppppp"
    else:
        reply_text = "ขอโทษค่ะ ฉันไม่เข้าใจคำสั่งนี้ 😢 ลองพิมพ์ 'เมนู' เพื่อดูคำสั่งที่ใช้ได้ค่ะ!"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
