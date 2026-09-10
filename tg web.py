import asyncio
import threading
import queue
import re
import datetime
from datetime import timezone
import streamlit as st
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# Для підтримки роботи з локальними часовими поясами
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

# =====================================================================
# НАЛАШТУВАННЯ ЗАСТОСУНКУ (Ваші 11 чатів)
# =====================================================================
import os

# Зчитуємо змінні з Railway або зі secrets
API_ID = int(os.environ.get("API_ID") or st.secrets.get("API_ID", 33419246))
API_HASH = os.environ.get("API_HASH") or st.secrets.get("API_HASH", "c84604c332b20c91eb9be6d01d4bd1ae")
TG_SESSION = os.environ.get("TG_SESSION") or st.secrets.get("TG_SESSION")

TARGET_CHATS = [  
    -1002486466109, -1001681084215, -1002112233307,
    -1001855211672, -1001745595323, -1001641260594,
    -1002783917373, -1002146225839, -1001223955273,
    -1001823047630, -1001802360559, -1001633313537,
]

MAX_HISTORY_HOURS = 3 
# =====================================================================

# Налаштування сторінки: встановлюємо назву для вкладки та іконку папки
st.set_page_config(page_title="Збірка Всього Потроху", page_icon="📦", layout="wide")

# Впровадження кастомного CSS для редизайну інтерфейсу
st.markdown("""
    <style>
    /* Стилізація головного контейнера */
    .main .block-container {
        padding-top: 2rem;
        max-width: 900px;
    }
    
    /* Красивий заголовок з градієнтом */
    .main-title {
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        background: linear-gradient(45deg, #0088cc, #00c6ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
        padding-bottom: 5px;
    }
    .sub-title {
        color: #888888;
        font-size: 0.95rem;
        margin-bottom: 25px;
    }
    
    /* Стильні картки повідомлень (імітація месенджера) */
    .msg-card {
        background-color: rgba(255, 255, 255, 0.05);
        padding: 15px 20px;
        border-radius: 4px 12px 12px 4px;
        margin-bottom: 14px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        transition: transform 0.2s, background-color 0.2s;
    }
    .msg-card:hover {
        background-color: rgba(255, 255, 255, 0.08);
        transform: translateX(2px);
    }
    
    /* Шапка повідомлення (Автор та Час) */
    .msg-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        padding-bottom: 4px;
    }
    .msg-author {
        font-weight: 700;
        font-size: 0.95rem;
    }
    .msg-time {
        color: #888888;
        font-size: 0.8rem;
        font-style: italic;
    }
    
    /* Текст повідомлення */
    .msg-body {
        font-size: 1rem;
        line-height: 1.5;
        white-space: pre-wrap;
    }
    
    /* Повідомлення про порожню стрічку */
    .empty-state {
        text-align: center;
        padding: 40px;
        color: #888888;
        border: 2px dashed rgba(255, 255, 255, 0.1);
        border-radius: 12px;
    }
    </style>
""", unsafe_allow_html=True)

# Назва застосунку на сторінці
st.markdown("<h1 class='main-title'>📦 Збірка Всього Потроху</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-title'>Агрегатор повідомлень та свіжих новин у реальному часі</p>", unsafe_allow_html=True)

if TG_SESSION:
    SESSION_DATA = StringSession(TG_SESSION)
else:
    st.error("Помилка: Не знайдено секрет TG_SESSION!")
    st.stop()

# --- ГЛОБАЛЬНЕ СХОВИЩЕ ДЛЯ ВСІХ СЕСІЙ ---
@st.cache_resource
def get_global_state():
    return {
        "history_buffer": [],      
        "history_ready": False     
    }

global_state = get_global_state()


# --- ФУНКЦІЯ АВТОМАТИЧНОЇ ГЕНЕРАЦІЇ СТАБІЛЬНОГО КОЛЬОРУ ДЛЯ КАНАЛУ ---
def get_channel_color(name):
    colors = [
        "#0088cc", "#2ecc71", "#9b59b6", "#e67e22", "#e74c3c", 
        "#1abc9c", "#f1c40f", "#34495e", "#ff4757", "#20bf6b",
        "#a55eea", "#fa8231", "#4b0082", "#00ced1", "#ff1493"
    ]
    hash_value = sum(ord(char) for char in name)
    return colors[hash_value % len(colors)]

# --- ФУНКЦІЯ ОЧИЩЕННЯ ТЕКСТУ ВІД ПОСИЛАНЬ ---
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(t\.me|tg://)\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'\n\s*\n+', '\n', text).strip()
    return text

# Повертаємо структурований словник із сирим datetime об'єктом (UTC)
async def process_and_enqueue(event_or_message):
    try:
        # Побудовано спеціально для нових постів у каналах (підтягує реальну назву)
        chat = await event_or_message.get_chat()
        if chat and hasattr(chat, 'title'):
            sender_name = chat.title
        else:
            sender = await event_or_message.get_sender()
            sender_name = getattr(sender, 'title', getattr(sender, 'first_name', 'Канал'))
    except Exception:
        sender_name = "Канал"

    cleaned_message = clean_text(event_or_message.text)
    if not cleaned_message:
        return None
        
    msg_date = event_or_message.date
    if not msg_date:
        msg_date = datetime.datetime.now(timezone.utc)
        
    return {"sender": sender_name, "raw_date": msg_date.astimezone(timezone.utc), "text": cleaned_message}

# --- ФУНКЦІЯ ОЧИЩЕННЯ СТАРОЇ ІСТОРІЇ НА СЕРВЕРІ ---
def clean_old_server_history():
    now = datetime.datetime.now(timezone.utc)
    cutoff_time = now - datetime.timedelta(hours=MAX_HISTORY_HOURS)
    global_state["history_buffer"] = [
        item for item in global_state["history_buffer"] 
        if isinstance(item, tuple) and len(item) > 1 and item[0] >= cutoff_time
    ]

# --- РОБОЧИЙ ПОТОК TELEGRAM ---
@st.cache_resource
def start_telegram_worker():
    client = TelegramClient(SESSION_DATA, API_ID, API_HASH)

    @client.on(events.NewMessage(chats=TARGET_CHATS))
    async def handle_new_message(event):
        msg_data = await process_and_enqueue(event)
        if msg_data:
            now = datetime.datetime.now(timezone.utc)
            global_state["history_buffer"].append((now, msg_data))
            clean_old_server_history()

    async def preload_history():
        time_limit = datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=1)
        all_messages = []
        
        for chat_id in TARGET_CHATS:
            try:
                async for message in client.iter_messages(chat_id, limit=15):
                    if message.date and message.date >= time_limit:
                        all_messages.append(message)
            except Exception:
                continue
                
        all_messages.sort(key=lambda m: m.date or time_limit)
        
        existing_texts = set()
        for item in global_state["history_buffer"]:
            if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], dict) and "text" in item[1]:
                existing_texts.add(item[1]["text"])
        
        for msg in all_messages:
            formatted = await process_and_enqueue(msg)
            msg_date = msg.date or time_limit
            if formatted and formatted["text"] not in existing_texts:
                global_state["history_buffer"].append((msg_date, formatted))
                existing_texts.add(formatted["text"])
                    
        global_state["history_ready"] = True

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            with client:
                loop.run_until_complete(preload_history())
                loop.run_until_complete(client.get_dialogs())
                loop.run_until_complete(client.run_until_disconnected())
        except Exception as e:
            print(f"Помилка у робочому потоці Telegram: {e}")
        finally:
            try:
                if client.is_connected():
                    loop.run_until_complete(client._disconnect())
                loop.close()
            except Exception:
                pass

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

client = start_telegram_worker()

# --- ⏱️ СУПЕР-КЕШУВАННЯ СТРІЧКИ ДЛЯ 1000 КОРИСТУВАЧІВ ---
# Зберігає готовий зліпок новин на 4 секунди у пам'яті. 
# Завдяки цьому сервер не робить індивідуальні важкі запити для кожного відвідувача.
@st.cache_data(ttl=4)
def get_cached_news():
    raw_history = list(global_state["history_buffer"])
    # Сортування: найновіші повідомлення завжди відображаються зверху сторінки
    raw_history.sort(key=lambda x: x[0] if isinstance(x, tuple) else datetime.datetime.now(timezone.utc), reverse=True)
    return [item[1] for item in raw_history if isinstance(item, tuple) and len(item) > 1 and isinstance(item[1], dict)]

# --- ВІДОБРАЖЕННЯ СТРІЧКИ (Оновлення кожні 4 секунди) ---
@st.fragment(run_every=4)
def display_feed():
    if not global_state["history_ready"]:
        st.info("⏳ «Збірка» підключається та формує стрічку новин. Повідомлення з'являться за мить...")
        return

    # Завантажуємо заморожену копію новин із кешу
    news_feed = get_cached_news()
            
    if not news_feed:
        st.markdown("<div class='empty-state'>📭 У вашій стрічці поки що немає повідомлень. Очікуємо на нові публікації...</div>", unsafe_allow_html=True)
        return

    # Динамічно отримуємо часовий пояс користувача з його браузера
    try:
        user_tz_str = st.context.timezone or "Europe/Kyiv"
        user_tz = zoneinfo.ZoneInfo(user_tz_str)
    except Exception:
        user_tz = zoneinfo.ZoneInfo("Europe/Kyiv")

    # Рендеринг повідомлень
    for msg in news_feed:
        line_color = get_channel_color(msg['sender'])
        
        if "raw_date" in msg:
            local_dt = msg["raw_date"].astimezone(user_tz)
            time_str = local_dt.strftime("%H:%M:%S")
        else:
            time_str = datetime.datetime.now(user_tz).strftime("%H:%M:%S")
        
        card_html = f"""
        <div class="msg-card" style="border-left: 4px solid {line_color};">
            <div class="msg-header">
                <span class="msg-author" style="color: {line_color};">&#128100; {msg['sender']}</span>
                <span class="msg-time">&#128338; {time_str}</span>
            </div>
            <div class="msg-body">{msg['text']}</div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

# Запуск відображення
display_feed()
