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
# НАЛАШТУВАННЯ ЗАСТОСУНКУ (Ваші 9 чатів)
# =====================================================================
API_ID = 33419246
API_HASH = 'c84604c332b20c91eb9be6d01d4bd1ae'

TARGET_CHATS = [  
    -1002486466109, -1001206439755, -1001681084215,
    -1001855211672, -1001745595323, -1002060414600,
    -1002783917373, -1001777491812, -1001823047630,
    -1001679424866, -1001855211672,
]
# =====================================================================

st.set_page_config(page_title="TG Web Reader", page_icon="💬", layout="centered")
st.title("📥 Збірка Всього По троху")

if "TG_SESSION" in st.secrets:
    SESSION_DATA = StringSession(st.secrets["TG_SESSION"])
else:
    st.error("Помилка: Не знайдено секрет TG_SESSION в налаштуваннях Streamlit Cloud!")
    st.stop()

# --- СЛОВНИК ДЛЯ РЕЄСТРАЦІЇ ПЕРСОНАЛЬНИХ ЧЕРГ КОРИСТУВАЧІВ ---
@st.cache_resource
def get_global_state():
    return {
        "active_queues": set(), # Множина всіх підключених черг користувачів
        "client": None          # Тут зберігатиметься клієнт Telegram
    }

global_state = get_global_state()

# Ініціалізація індивідуального сховища повідомлень для поточної вкладки/пристрою
if "msg_store" not in st.session_state:
    st.session_state.msg_store = ["🔄 Підключення... Завантажуємо свіжу історію за 30 хвилин..."]

# Створення унікальної черги для КОЖНОГО окремого пристрою/сесії
if "user_queue" not in st.session_state:
    user_queue = queue.Queue()
    st.session_state.user_queue = user_queue
    global_state["active_queues"].add(user_queue) # Реєструємо чергу в глобальному списку розсилки

# --- ФУНКЦІЯ ОЧИЩЕННЯ ТЕКСТУ ВІД ПОСИЛАНЬ ---
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(t\.me|tg://)\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'\n\s*\n+', '\n', text).strip()
    return text

# Спільна функція форматування повідомлення
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
        
    return f"**👤 Від:** {sender_name}\n\n💬 {cleaned_message}"

@st.cache_resource
def start_telegram_worker():
    client = TelegramClient(SESSION_DATA, API_ID, API_HASH)
    global_state["client"] = client

    @client.on(events.NewMessage(chats=TARGET_CHATS))
    async def handle_new_message(event):
        full_text = await process_and_enqueue(event)
        if full_text:
            # НАДВАЖЛИВО: Дублюємо нове повідомлення в черги ВСІХ активних пристроїв
            # Створюємо копію множини, щоб уникнути помилок під час ітерації
            for q in list(global_state["active_queues"]):
                q.put(full_text)

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client.start()
        loop.run_until_complete(client.get_dialogs())
        loop.run_until_complete(client.run_until_disconnected())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

# Запуск фонового клієнта Telegram
start_telegram_worker()

# --- ФУНКЦІЯ ЗАВАНТАЖЕННЯ ІСТОРІЇ ПРИ ВХОДІ КОНКРЕТНОГО КОРИСТУВАЧА ---
@st.cache_data(ttl=10) # Кешуємо запит на 10 секунд, щоб не спамити Telegram при перезавантаженні сторінки
def fetch_history_from_tg():
    client = global_state["client"]
    if not client:
        return []
        
    # Створюємо новий event loop для синхронного виклику асинхронного методу Telethon всередині Streamlit
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def get_history():
        time_limit = datetime.datetime.now(timezone.utc) - datetime.timedelta(minutes=30)
        all_messages = []
        for chat_id in TARGET_CHATS:
            try:
                async for message in client.iter_messages(chat_id, offset_date=time_limit, reverse=True):
                    if message.date and message.date >= time_limit:
                        all_messages.append(message)
            except Exception:
                continue
        
        all_messages.sort(key=lambda m: m.date or time_limit)
        
        processed_strings = []
        for msg in all_messages:
            text = loop.run_until_complete(process_and_enqueue(msg))
            if text:
                processed_strings.append(text)
        return processed_strings

    try:
        return loop.run_until_complete(get_history())
    finally:
        loop.close()

# Завантажуємо історію за останні 30 хвилин ТІЛЬКИ ОДИН РАЗ під час першого візиту цієї сесії
if "history_loaded" not in st.session_state:
    history_msgs = fetch_history_from_tg()
    if history_msgs:
        st.session_state.msg_store = history_msgs
    else:
        st.session_state.msg_store = ["📭 За останні 30 хвилин повідомлень немає. Чекаємо на нові..."]
    st.session_state.history_loaded = True

# Кнопка очищення очистить стрічку ТІЛЬКИ для поточного користувача
if st.button("🧹 Очистити мою стрічку"):
    st.session_state.msg_store = ["🧹 Стрічку очищено. Очікуємо нові пости..."]
    st.rerun()

st.write("---")

# Стрічка оновлюється кожні 2 секунди автономно для кожного екрана
@st.fragment(run_every=2)
def display_feed():
    current_queue = st.session_state.user_queue
    while not current_queue.empty():
        try:
            msg = current_queue.get_nowait()
            if msg not in st.session_state.msg_store:
                st.session_state.msg_store.append(msg)
        except queue.Empty:
            break
            
    for msg in reversed(st.session_state.msg_store):
        st.info(msg)

display_feed()
