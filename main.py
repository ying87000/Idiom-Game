import os
import random
import json # 用於將字典序列化存入 Redis
from dotenv import load_dotenv
from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

import redis # 引入 redis

# 載入 .env 檔案中的環境變數
load_dotenv()

app = Flask(__name__)

# Line Bot 設定
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    print("錯誤: 請設定 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 環境變數")
    exit()

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# Redis 連接
# Heroku 會自動設定 REDIS_URL 環境變數，若本地測試則使用 .env 中的設定
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
try:
    redis_client = redis.from_url(REDIS_URL)
    redis_client.ping() # 測試連接
    print("成功連接到 Redis!")
except redis.exceptions.ConnectionError as e:
    print(f"錯誤: 無法連接到 Redis: {e}")
    print("請確保 Redis 伺服器正在運行，並且 REDIS_URL 設定正確。")
    # 你可以在這裡決定是否要 exit()，或者讓應用在沒有 Redis 的情況下降級 (但此範例依賴 Redis)
    exit()


# 詞庫載入
WORD_LIST = set()
def load_words(filename="words.txt"):
    global WORD_LIST
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            WORD_LIST = {line.strip() for line in f if line.strip() and len(line.strip()) >= 2} # 至少兩個字
        if not WORD_LIST:
            print(f"警告: 詞庫 {filename} 為空或格式不正確。")
            # 可以提供一個最小的備用詞庫
            WORD_LIST = {"遊戲人間", "間不容髮", "髮指眥裂", "裂石穿雲", "雲淡風輕"}
            print(f"已載入備用詞庫，共 {len(WORD_LIST)} 個詞。")
        else:
            print(f"成功載入 {len(WORD_LIST)} 個詞語。")
    except FileNotFoundError:
        print(f"錯誤: 詞庫檔案 {filename} 未找到。")
        WORD_LIST = {"遊戲人間", "間不容髮", "髮指眥裂"}
        print("已載入備用詞庫。")

load_words()

# 遊戲指令
CMD_START_GAME = ["開始遊戲", "start", "開始", "重來", "restart"]
CMD_GIVE_UP = ["放棄", "give up", "投降", "結束遊戲"]

def get_user_state(user_id):
    """從 Redis 獲取用戶狀態，若不存在則初始化"""
    state_json = redis_client.get(user_id)
    if state_json:
        return json.loads(state_json)
    else:
        # 初始化新用戶狀態
        default_state = {'last_word': None, 'used_words': [], 'game_active': False} # used_words 改為 list 以便 json 序列化
        save_user_state(user_id, default_state)
        return default_state

def save_user_state(user_id, state):
    """將用戶狀態存儲到 Redis"""
    # 確保 used_words 是 list，因為 set 不能直接 json.dumps
    if isinstance(state.get('used_words'), set):
        state['used_words'] = list(state['used_words'])
    redis_client.set(user_id, json.dumps(state))

def reset_user_game(user_id, state):
    """重置用戶遊戲狀態"""
    state['last_word'] = None
    state['used_words'] = []
    state['game_active'] = True # 開始遊戲時直接設為 active
    save_user_state(user_id, state)

def reply_message_text(reply_token, text):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    state = get_user_state(user_id)
    # 將 used_words 從 list 轉回 set 以方便操作，儲存時再轉回 list
    current_used_words = set(state.get('used_words', []))


    if user_text.lower() in CMD_START_GAME:
        reset_user_game(user_id, state)
        reply_text = "詞語接龍開始！請你先說一個詞語 (建議四字詞語)。"
        reply_message_text(event.reply_token, reply_text)
        return

    if user_text.lower() in CMD_GIVE_UP:
        if state['game_active']:
            state['game_active'] = False
            save_user_state(user_id, state) # 保存狀態，標記遊戲結束
            reply_text = "好吧，遊戲結束。\n輸入「開始遊戲」可以再玩一局。"
        else:
            reply_text = "遊戲尚未開始，無法放棄喔。\n輸入「開始遊戲」來啟動。"
        reply_message_text(event.reply_token, reply_text)
        return

    if not state['game_active']:
        reply_text = "遊戲尚未開始。請輸入「開始遊戲」來啟動，或「放棄」來確認。"
        reply_message_text(event.reply_token, reply_text)
        return

    # --- 遊戲進行中 ---
    if not user_text or len(user_text) < 2: # 簡單的詞語長度檢查
        reply_text = "請輸入至少兩個字的詞語喔！"
        reply_message_text(event.reply_token, reply_text)
        return

    if user_text not in WORD_LIST:
        reply_text = f"「{user_text}」不在我的詞典裡喔，換一個吧！"
        reply_message_text(event.reply_token, reply_text)
        return

    if user_text in current_used_words:
        reply_text = f"「{user_text}」已經用過了，換一個吧！"
        reply_message_text(event.reply_token, reply_text)
        return

    if state['last_word'] and user_text[0] != state['last_word'][-1]:
        reply_text = f"「{user_text}」沒有接上「{state['last_word'][-1]}」哦，再試一次！"
        reply_message_text(event.reply_token, reply_text)
        return

    # 使用者詞語合法
    current_used_words.add(user_text)
    state['last_word'] = user_text
    last_char_user = user_text[-1]

    # 機器人找詞回應
    possible_bot_words = [
        word for word in WORD_LIST
        if word.startswith(last_char_user) and word not in current_used_words
    ]

    if not possible_bot_words:
        reply_text = f"你太厲害了！「{last_char_user}」開頭的詞我想不到了，你贏了！\n輸入「開始遊戲」可以再玩一局。"
        state['game_active'] = False # 遊戲結束
    else:
        bot_word = random.choice(possible_bot_words)
        current_used_words.add(bot_word)
        state['last_word'] = bot_word
        reply_text = bot_word

    state['used_words'] = list(current_used_words) # 更新回 state 中
    save_user_state(user_id, state) # 保存遊戲進度
    reply_message_text(event.reply_token, reply_text)


if __name__ == "__main__":
    # 本地運行時，PORT 可以自訂；Heroku 會提供 PORT 環境變數
    port = int(os.environ.get('PORT', 5000))
    # debug=True 不應在生產環境 (如 Heroku) 中使用 gunicorn 時開啟
    # gunicorn 會處理多進程和日誌等
    # 如果直接用 python app.py 運行，可以開啟 debug=True
    # 但部署到 Heroku 時，Procfile 中的 gunicorn 命令會生效
    if os.getenv('FLASK_ENV') == 'development' or not os.getenv('PORT'): # 簡單判斷是否本地開發
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        # 在 Heroku 等環境中，gunicorn 會處理服務的啟動
        # 此處的 app.run 不會被執行，除非直接執行 python app.py
        # 為了避免在 Heroku 上意外執行 Flask 的開發伺服器，可以不加這段
        # 或者讓 gunicorn 在 Procfile 中直接指定 app:app 即可
        pass
