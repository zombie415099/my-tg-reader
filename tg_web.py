import asyncio
import threading
import queue
import re
import datetime
from datetime import timezone
import streamlit as st
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# =====================================================================
# НАЛАШТУВАННЯ ЗАСТОСУНКУ (Ваші 11 чатів)
# =====================================================================
API_ID = 33419246
API_HASH = 'c84604c332b20c91eb9be6d01d4bd1ae'

TARGET_CHATS = [  
    -1002486466109, -1001206439755, -1001681084215,
    -1001855211672, -1001745595323, -1002060414600,
    -1002783917373, -1001777491812, -1001823047630,
    -1001679424866, -1001855211672,
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

if "TG_SESSION" in st.secrets:
    SESSION_DATA = StringSession(st.secrets["TG_SESSION"])
else:
    st.error("Помилка: Не знайдено секрет TG_SESSION в налаштуваннях Streamlit Cloud!")
    st.stop()

# --- ГЛОБАЛЬНЕ СХОВИЩЕ ДЛЯ ВСІХ СЕСІЙ ---
@st.cache_resource
def get_global_state():
    return {
        "active_queues": set(),    
        "history_buffer": [],      
        "history_ready": False     
    }

global_state = get_global_state()

# --- РОЗУМНА ЧЕРГА З АВТООЧИЩЕННЯМ ---
class AutoCleanupQueue(queue.Queue):
    def __init__(self, global_set):
        super().__init__()
        self.global_set = global_set
        self.global_set.add(self)

    def __del__(self):
        try:
            self.global_set.discard(self)
        except Exception:
            pass

if "msg_store" not in st.session_state:
    st.session_state.msg_store = []

if "user_queue" not in st.session_state:
    st.session_state.user_queue = AutoCleanupQueue(global_state["active_queues"])

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

# Повертаємо структурований словник замість сирого тексту
async def process_and_enqueue(event_or_message):
    try:
        if hasattr(event_or_message, 'get_sender'):
            sender = await event_or_message.get_sender()
        else:
            sender = event_or_message.sender
        sender_name = getattr(sender, 'title', getattr(sender, 'first_name', 'Канал'))
    except Exception:
        sender_name = "Канал"
        
    cleaned_message = clean_text(event_or_message.text)
    if not cleaned_message:
        return None
        
    msg_date = event_or_message.date
    if msg_date:
        local_time = msg_date.astimezone()
        time_str = local_time.strftime("%H:%M:%S")
    else:
        time_str = datetime.datetime.now().strftime("%H:%M:%S")
        
    return {"sender": sender_name, "time": time_str, "text": cleaned_message}

# --- ФУНКЦІЯ ОЧИЩЕННЯ СТАРОЇ ІСТОРІЇ НА СЕРВЕРІ ---
def clean_old_server_history():
    now = datetime.datetime.now(timezone.utc)
    cutoff_time = now - datetime.timedelta(hours=MAX_HISTORY_HOURS)
    global_state["history_buffer"] = [
        item for item in global_state["history_buffer"] if item[0] >= cutoff_time
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
            
            for q in list(global_state["active_queues"]):
                try:
                    q.put(msg_data)
                except Exception:
                    continue

    async def preload_history():
        # Оптимізовано: збираємо за останні 45 хвилин для прискорення
        time_limit = datetime.datetime.now(timezone.utc) - datetime.timedelta(minutes=45)
        all_messages = []
        
        for chat_id in TARGET_CHATS:
            try:
                # Оптимізовано: зменшено ліміт до 15 повідомлень на чат, щоб Telegram не блокував швидкість
                async for message in client.iter_messages(chat_id, limit=15, offset_date=time_limit, reverse=True):
                    if message.date and message.date >= time_limit:
                        all_messages.append(message)
            except Exception:
                continue
                
        all_messages.sort(key=lambda m: m.date or time_limit)
        
        # Швидке створення кешу унікальних текстів
        existing_texts = set(item[1]["text"] for item in global_state["history_buffer"])
        
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
        client.start()
        loop.run_until_complete(preload_history())
        loop.run_until_complete(client.get_dialogs())
        loop.run_until_complete(client.run_until_disconnected())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

start_telegram_worker()

# --- ЛОГІКА ПЕРШОГО ЗАХОДУ КОРИСТУВАЧА ---
if "initial_load_done" not in st.session_state:
    if global_state["history_ready"]:
        st.session_state.msg_store = [item[1] for item in global_state["history_buffer"]]
        st.session_state.initial_load_done = True
    else:
        st.info("⏳ «Збірка» підключається та формує стрічку новин. Повідомлення з'являться за мить...")
        st.fragment(run_every=2)(lambda: st.rerun())()

# Панель керування зверху
col_info, col_btn = st.columns([0.75, 0.25], vertical_alignment="center")
with col_info:
    st.caption(f"📡 Активний моніторинг чатів. Оновлення кожні 2 секунди. Буфер: {MAX_HISTORY_HOURS} год.")
with col_btn:
    if st.button("🧹 Очистити стрічку", use_container_width=True):
        st.session_state.msg_store = []
        st.rerun()

st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

# --- ВІДОБРАЖЕННЯ СТРІЧКИ (Оновлення кожні 2 секунди) ---
@st.fragment(run_every=2)
def display_feed():
    current_queue = st.session_state.user_queue
    
    while not current_queue.empty():
        try:
            msg = current_queue.get_nowait()
            if not any(existing_msg["text"] == msg["text"] for existing_msg in st.session_state.msg_store):
                st.session_state.msg_store.append(msg)
        except queue.Empty:
            break
            
    if not st.session_state.msg_store:
        st.markdown("📭 У вашій стрічці поки що немає повідомлень. Очікуємо на нові публікації...", unsafe_allow_html=True)
        return
        # Рендеринг повідомлень у вигляді кастомних HTML-карток
        for msg in reversed(st.session_state.msg_store):
            line_color = get_channel_color(msg['sender'])
            # Формуємо HTML-код картки
        card_html = f''
        f''
        f'👤 {msg["sender"]}'
        f'🕒 {msg["time"]}'
        f''
        f'{msg["text"]}'
        f''
        st.markdown(card_html, unsafe_allow_html=True)
        if "initial_load_done" in st.session_state:
            display_feed()
