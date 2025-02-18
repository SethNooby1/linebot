from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.getenv("2006928117")
LINE_SECRET = os.getenv("84262e42120bc8acb109d4f1a0fcb17b")

line_bot_api = LineBotApi(2006928117)
handler = WebhookHandler(84262e42120bc8acb109d4f1a0fcb17b)

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
    reply_text = "Hello! You said: " + user_message
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run(port=5000)
