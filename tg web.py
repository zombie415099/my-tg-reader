import asyncio
import os
import re
import datetime
from datetime import timezone
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from telethon import TelegramClient, events
from telethon.sessions import StringSession

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

# =====================================================================
# НАЛАШТУВАННЯ
# =====================================================================
API_ID = int(os.environ.get("API_ID", 33419246))
API_HASH = os.environ.get("API_HASH", "c84604c332b20c91eb9be6d01d4bd1ae")
TG_SESSION = os.environ.get("TG_SESSION")

TARGET_CHATS = [  
    -1002486466109, -1001681084215, -1002112233307,
    -1001855211672, -1001745595323, -1001641260594,
    -1002783917373, -1002146225839, -1001223955273,
    -1001823047630, -1001802360559, -1001633313537,
]

MAX_HISTORY_HOURS = 3

# Глобальне сховище новин у пам'яті сервера
HISTORY_BUFFER = []
HISTORY_READY = False

app = FastAPI()

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
def get_channel_color(name):
    colors = ["#0088cc", "#2ecc71", "#9b59b6", "#e67e22", "#e74c3c", "#1abc9c", "#f1c40f", "#34495e"]
    hash_value = sum(ord(char) for char in name)
    return colors[hash_value % len(colors)]

def clean_text(text):
    if not text: return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(t\.me|tg://)\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    return re.sub(r'\n\s*\n+', '\n', text).strip()

async def process_message(event_or_message):
    try:
        chat = await event_or_message.get_chat()
        sender_name = getattr(chat, 'title', 'Канал')
    except Exception:
        sender_name = "Канал"

    cleaned = clean_text(event_or_message.text)
    if not cleaned: return None
        
    msg_date = event_or_message.date or datetime.datetime.now(timezone.utc)
    return {"sender": sender_name, "raw_date": msg_date.astimezone(timezone.utc), "text": cleaned}

def clean_old_history():
    global HISTORY_BUFFER
    cutoff = datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=MAX_HISTORY_HOURS)
    HISTORY_BUFFER = [item for item in HISTORY_BUFFER if item["raw_date"] >= cutoff]

# --- TELEGRAM WORKER ---
async def start_telegram():
    global HISTORY_READY, HISTORY_BUFFER
    if not TG_SESSION:
        print("Помилка: Не знайдено TG_SESSION!")
        return

    client = TelegramClient(StringSession(TG_SESSION), API_ID, API_HASH)

    @client.on(events.NewMessage(chats=TARGET_CHATS))
    async def handle_new_message(event):
        msg_data = await process_message(event)
        if msg_data:
            HISTORY_BUFFER.append(msg_data)
            clean_old_history()

    await client.connect()
    
    # Завантаження історії за 1 годину
    time_limit = datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=1)
    existing_texts = set()
    
    for chat_id in TARGET_CHATS:
        try:
            async for message in client.iter_messages(chat_id, limit=15):
                if message.date and message.date >= time_limit:
                    formatted = await process_message(message)
                    if formatted and formatted["text"] not in existing_texts:
                        HISTORY_BUFFER.append(formatted)
                        existing_texts.add(formatted["text"])
        except Exception:
            continue
            
    HISTORY_READY = True
    print("Telegram клієнт успішно запущений та історія завантажена!")
    await client.run_until_disconnected()

# Запуск Telegram клієнта паралельно з сервером при старті
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_telegram())

# --- ВЕБ-СТОРІНКА (ФРОНТЕНД) ---
@app.get("/", response_class=HTMLResponse)
async def read_root():
    sorted_news = sorted(HISTORY_BUFFER, key=lambda x: x["raw_date"], reverse=True)
    user_tz = zoneinfo.ZoneInfo("Europe/Kyiv")

    cards_html = ""
    if not HISTORY_READY and not sorted_news:
        cards_html = "<div class='empty-state'>⏳ Завантаження новин, зачекайте кілька секунд... Сторінка оновиться автоматично.</div>"
    elif not sorted_news:
        cards_html = "<div class='empty-state'>📭 Немає свіжих новин за останні години.</div>"
    else:
        for msg in sorted_news:
            color = get_channel_color(msg["sender"])
            time_str = msg["raw_date"].astimezone(user_tz).strftime("%H:%M:%S")
            cards_html += f"""
            <div class="msg-card" style="border-left: 4px solid {color};">
                <div class="msg-header">
                    <span class="msg-author" style="color: {color};">&#128100; {msg['sender']}</span>
                    <span class="msg-time">&#128338; {time_str}</span>
                </div>
                <div class="msg-body">{msg['text']}</div>
            </div>
            """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Збірка Всього Потроху</title>
        {"<meta http-equiv='refresh' content='10'>" if not HISTORY_READY else ""}
        <link href="https://googleapis.com" rel="stylesheet">
        <style>
            body {{ font-family: 'Inter', sans-serif; background-color: #0e1117; color: #ffffff; margin: 0; padding: 2rem 1rem; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            .main-title {{ font-weight: 800; font-size: 2.5rem; background: linear-gradient(45deg, #0088cc, #00c6ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0 0 5px 0; }}
            .sub-title {{ color: #888888; font-size: 0.95rem; margin-bottom: 25px; }}
            .msg-card {{ background-color: rgba(255, 255, 255, 0.05); padding: 15px 20px; border-radius: 4px 12px 12px 4px; margin-bottom: 14px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05); }}
            .msg-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom: 4px; }}
            .msg-author {{ font-weight: 700; font-size: 0.95rem; }}
            .msg-time {{ color: #888888; font-size: 0.8rem; font-style: italic; }}
            .msg-body {{ font-size: 1rem; line-height: 1.5; white-space: pre-wrap; }}
            .empty-state {{ text-align: center; padding: 40px; color: #888888; border: 2px dashed rgba(255, 255, 255, 0.1); border-radius: 12px; }}
            .refresh-btn {{ background: #0088cc; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="main-title">📦 Збірка Всього Потроху</h1>
            <p class="sub-title">Агрегатор повідомлень та свіжих новин у реальному часі</p>
            <button class="refresh-btn" onclick="window.location.reload();">🔄 Оновити новини</button>
            <div id="feed">
                {cards_html}
            </div>
        </div>

        <script>
            setTimeout(function(){{
                window.location.reload();
            }}, 4000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)
