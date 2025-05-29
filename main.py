import os
import random
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

with open("words.txt", encoding="utf-8") as f:
    WORD_LIST = [line.strip() for line in f if line.strip()]
WORD_SET = set(WORD_LIST)

user_data = {}

START_COMMANDS = {"開始", "重新開始", "start", "Start"}
END_COMMANDS = {"結束", "放棄", "quit", "Quit"}

@app.route("/")
def home():
    return "成語接龍機器人啟動成功！"

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
def is_real_word(word):
    """
    使用萌典查詢詞語是否存在
    """
    url = f"https://www.moedict.tw/{word}"
    resp = requests.get(url)

    if resp.status_code == 200 and "沒有這個詞" not in resp.text:
        return True
    return False

def add_word_to_dict(word):
    with open("words.txt", "a", encoding="utf-8") as f:
        f.write(f"{word}\n")
    word_list.append(word)
    word_set.add(word)

def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    if user_id not in user_data:
        user_data[user_id] = {"score": 0, "last_word": "", "playing": False}

    data = user_data[user_id]

    if text in START_COMMANDS:
        data["playing"] = True
        data["score"] = 0
        data["last_word"] = random.choice(WORD_LIST)
        reply = f"接龍開始！第一個詞是：「{data['last_word']}」"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    elif text in END_COMMANDS:
        data["playing"] = False
        score = data["score"]
        reply = f"接龍結束！你總共接對了 {score} 個詞～"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    elif not data["playing"]:
        reply = "請先輸入「開始」或「Start」來開始接龍喔～"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    if text not in word_set:
        if is_real_word(text):
            add_word_to_dict(text)
            reply = f"「{text}」是個新詞唷，我已經學會它了！👍"
        else:
            reply = f"「{text}」不是有效的詞語或成語唷～"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )
        return

    prev = data["last_word"]
    if text[0] != prev[-1]:
        reply = f"要用「{prev[-1]}」開頭的詞才行喔～你用了「{text}」"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    candidates = [w for w in WORD_LIST if w[0] == text[-1]]
    if not candidates:
        reply = f"我想不到「{text[-1]}」開頭的詞了...你贏了！👏"
        data["playing"] = False
    else:
        next_word = random.choice(candidates)
        data["score"] += 1
        data["last_word"] = next_word
        reply = f"接得好～我接：「{next_word}」！換你～（目前得分：{data['score']}）"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
