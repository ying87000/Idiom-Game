import os
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# LINE Channel Access Token 和 Secret
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# 儲存使用者最後一個詞
user_last_word = {}

# 讀取詞庫
def load_words():
    with open("words.txt", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

word_list = load_words()
word_set = set(word_list)  # 加快查詢速度

# 檢查詞語是否有效（使用萌典 API）
def is_valid_word(word):
    url = f"https://www.moedict.tw/{word}.json"
    try:
        response = requests.get(url)
        return response.status_code == 200
    except:
        return False

# 新增詞語到詞庫
def append_word_to_dict(word):
    with open("words.txt", "a", encoding="utf-8") as f:
        f.write(word + "\n")
    word_list.append(word)
    word_set.add(word)

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

    # 判斷是否為特殊指令（開始/結束）
    if msg in ['開始', '重新開始', 'start', 'Start']:
        user_last_word[user_id] = '開始'
        reply = "遊戲開始！請輸入第一個詞語～"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
    if msg in ['結束', '放棄', 'quit', 'Quit']:
        user_last_word[user_id] = '開始'
        reply = "遊戲結束～想玩再說一聲「開始」喔！"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # 詞語不存在於詞庫中 → 查詢是否為有效詞語
    if msg not in word_set:
        if is_valid_word(msg):
            append_word_to_dict(msg)
            note = f"「{msg}」是新詞，我幫你加進詞庫囉！👍"
        else:
            reply = f"「{msg}」不是有效的詞語或成語唷～"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
    else:
        note = ""

    prev = user_last_word.get(user_id, "開始")

    if prev != "開始":
        if msg[0] != prev[-1]:
            reply = f"要用「{prev[-1]}」開頭的詞語或成語才行！你用了「{msg}」"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

    # 找出可接續詞語
    next_candidates = [word for word in word_list if word[0] == msg[-1]]

    if not next_candidates:
        reply = f"{note}\n我想不到「{msg[-1]}」開頭的詞語了...你贏啦！👏"
        user_last_word[user_id] = "開始"  # 重設
    else:
        next_word = next_candidates[0]
        reply = f"{note}\n接得好～我接：「{next_word}」！換你～"
        user_last_word[user_id] = next_word

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply.strip()))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=81)
