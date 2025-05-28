import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

user_last_word = {}

def load_words():
    with open("words.txt", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

word_list = load_words()
word_set = set(word_list)

@app.route("/")
def home():
    return "接龍機器人啟動成功！"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    if msg not in word_set:
        reply = f"「{msg}」不是有效的詞語或成語唷～"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )
        return

    prev = user_last_word.get(user_id, "開始")

    if prev != "開始":
        if msg[0] != prev[-1]:
            reply = f"要用「{prev[-1]}」開頭的詞語或成語才行！你用了「{msg}」"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply)
            )
            return

    next_candidates = [word for word in word_list if word[0] == msg[-1]]

    if not next_candidates:
        reply = f"我想不到「{msg[-1]}」開頭的詞語或成語了...你贏啦！👏"
        user_last_word[user_id] = "開始"
    else:
        next_word = next_candidates[0]
        reply = f"接得好～我接：「{next_word}」！換你～"
        user_last_word[user_id] = next_word

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
