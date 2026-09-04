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
# =====================================================================

st.set_page_config(page_title="TG Web Reader", page_icon="💬", layout="centered")
st.title("📥 Збірка Всього По троху")

if "TG_SESSION" in st.secrets:
    SESSION_DATA = StringSession(st.secrets["TG_SESSION"])
else:
    st.error("Помилка: Не знайдено секрет TG_SESSION в налаштуваннях Streamlit Cloud!")
    st.stop()

@st.cache_resource
def get_message_queue():
    return queue.Queue()

if "msg_store" not in st.session_state:
    st.session_state.msg_store = ["🔄 Сервер запущено. Завантажуємо історію за останні 30 хвилин..."]

msg_queue = get_message_queue()

# --- ФУНКЦІЯ ОЧИЩЕННЯ ТЕКСТУ ВІД ПОСИЛАНЬ ---
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(t\.me|tg://)\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'\n\s*\n+', '\n', text).strip()
    return text

@st.cache_resource
def start_telegram_worker():
    client = TelegramClient(SESSION_DATA, API_ID, API_HASH)

    # Функція обробки для єдиного формату текстових повідомлень
    async def process_and_enqueue(event_or_message):
        try:
            # Спроба отримати назву відправника залежно від типу об'єкта
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

    @client.on(events.NewMessage(chats=TARGET_CHATS))
    async def handle_new_message(event):
        full_text = await process_and_enqueue(event)
        if full_text:
            msg_queue.put(full_text)

    # Асинхронна функція для завантаження історії повідомлень
    async def load_history(client):
        # Часова мітка 30 хвилин тому назад (в UTC, як працює Telegram)
        time_limit = datetime.datetime.now(timezone.utc) - datetime.timedelta(minutes=30)
        all_history_messages = []

        for chat_id in TARGET_CHATS:
            try:
                # Отримуємо повідомлення з кожного чату
                async for message in client.iter_messages(chat_id, offset_date=time_limit, reverse=True):
                    # Перевіряємо, чи повідомлення дійсно свіжіше за 30 хвилин
                    if message.date and message.date >= time_limit:
                        all_history_messages.append(message)
            except Exception as e:
                # Якщо бота забанили в якомусь чаті або чат не існує, ігноруємо помилку
                continue

        # Сортуємо всі знайдені повідомлення за часом створення (від старіших до новіших)
        all_history_messages.sort(key=lambda msg: msg.date or time_limit)

        # Додаємо оброблені повідомлення в чергу Streamlit
        for message in all_history_messages:
            full_text = await process_and_enqueue(message)
            if full_text:
                msg_queue.put(full_text)

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client.start()
        
        # Спершу завантажуємо історію, а вже потім запускаємо нескінченне слухання нових постів
        loop.run_until_complete(load_history(client))
        
        loop.run_until_complete(client.get_dialogs())
        loop.run_until_complete(client.run_until_disconnected())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

start_telegram_worker()

if st.button("🧹 Очистити стрічку"):
    st.session_state.msg_store = ["🧹 Стрічку очищено. Чекаємо на нові повідомлення..."]
    st.rerun()

st.write("---")

@st.fragment(run_every=2)
def display_feed():
    while not msg_queue.empty():
        try:
            msg = msg_queue.get_nowait()
            # Уникаємо дублікатів (наприклад, якщо повідомлення вже є в списку)
            if msg not in st.session_state.msg_store:
                st.session_state.msg_store.append(msg)
        except queue.Empty:
            break
            
    for msg in reversed(st.session_state.msg_store):
        st.info(msg)

display_feed()
