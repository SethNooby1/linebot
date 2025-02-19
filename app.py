from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import pytz
from datetime import datetime, time

app = Flask(__name__)

# Replace these with your actual credentials
LINE_ACCESS_TOKEN = "2006928117"
LINE_SECRET = "84262e42120bc8acb109d4f1a0fcb17b"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# Set your desired time zone
BANGKOK_TIMEZONE = pytz.timezone('Asia/Bangkok')

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
    print("Received message event:", event)
    user_message = event.message.text.lower()
    
    if user_message == "hi":
        reply_text = "hihiihihihihii"
    else:
        reply_text = "I'm sorry, I don't understand that. Type 'hi' for a test reply."
    
    print("Attempting to reply with:", reply_text)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# Function to check and send scheduled messages
def check_and_send_scheduled_messages():
    now = datetime.now(BANGKOK_TIMEZONE)
    current_time = now.time()
    print("Current time:", current_time)

    if time(19, 05) <= current_time <= time(19, 06):
        print("Sending scheduled message")
        line_bot_api.broadcast(TextSendMessage(text="testestesticle"))

# This function would need to be called periodically to check the time
# For testing, you might want to call this manually or use a scheduler like APScheduler if you deploy this
# Here's a simple way to call it manually for testing:

@app.route("/test_schedule", methods=["GET"])
def test_schedule():
    check_and_send_scheduled_messages()
    return "Scheduled message check executed."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)