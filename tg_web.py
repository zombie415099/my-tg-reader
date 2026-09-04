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

# --- ГЛОБАЛЬНЕ СХОВИЩЕ ДЛЯ ВСІХ СЕСІЙ ---
@st.cache_resource
def get_global_state():
    return {
        "active_queues": set(),    # Усі черги користувачів «наживо»
        "history_buffer": [],      # Сюди збережеться історія за 30 хв при старті
        "history_ready": False     # Прапор готовності історії
    }

global_state = get_global_state()

# --- ІНІЦІАЛІЗАЦІЯ ДЛЯ КОНКРЕТНОЇ ВКЛАДКИ КОРИСТУВАЧА ---
if "msg_store" not in st.session_state:
    st.session_state.msg_store = []

if "user_queue" not in st.session_state:
    user_queue = queue.Queue()
    st.session_state.user_queue = user_queue
    global_state["active_queues"].add(user_queue)

# --- ФУНКЦІЯ ОЧИЩЕННЯ ТЕКСТУ ВІД ПОСИЛАНЬ ---
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'(t\.me|tg://)\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'\n\s*\n+', '\n', text).strip()
    return text

# Форматування повідомлення
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

# --- РОБОЧИЙ ПОТОК TELEGRAM ---
@st.cache_resource
def start_telegram_worker():
    client = TelegramClient(SESSION_DATA, API_ID, API_HASH)

    # Обробник нових повідомлень (працює завжди наживо)
    @client.on(events.NewMessage(chats=TARGET_CHATS))
    async def handle_new_message(event):
        full_text = await process_and_enqueue(event)
        if full_text:
            # Розсилаємо копію повідомлення ВСІМ активним користувачам
            for q in list(global_state["active_queues"]):
                q.put(full_text)

    # Функція збору історії (виконується ОДИН РАЗ безпечно всередині потоку Telethon)
    async def preload_history():
        time_limit = datetime.datetime.now(timezone.utc) - datetime.timedelta(minutes=30)
        all_messages = []
        
        for chat_id in TARGET_CHATS:
            try:
                # Використовуємо ліміт у 20 повідомлень на чат, щоб не отримати бан за флуд
                async for message in client.iter_messages(chat_id, limit=20, offset_date=time_limit, reverse=True):
                    if message.date and message.date >= time_limit:
                        all_messages.append(message)
            except Exception:
                continue
                
        # Сортуємо від старіших до новіших
        all_messages.sort(key=lambda m: m.date or time_limit)
        
        # Обробляємо та зберігаємо в глобальний буфер
        for msg in all_messages:
            formatted = await process_and_enqueue(msg)
            if formatted and formatted not in global_state["history_buffer"]:
                global_state["history_buffer"].append(formatted)
                
        global_state["history_ready"] = True

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client.start()
        
        # Крок 1: Спочатку завантажуємо історію в безпечному середовищі
        loop.run_until_complete(preload_history())
        
        # Крок 2: Запускаємо постійне прослуховування нових повідомлень
        loop.run_until_complete(client.get_dialogs())
        loop.run_until_complete(client.run_until_disconnected())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

# Запуск фонового робота
start_telegram_worker()

# --- ЛОГІКА ПЕРШОГО ЗАХОДУ КОРИСТУВАЧА ---
if "initial_load_done" not in st.session_state:
    # Якщо історія у фоновому потоці вже зібрана — копіюємо її користувачу
    if global_state["history_ready"]:
        st.session_state.msg_store = list(global_state["history_buffer"])
        st.session_state.initial_load_done = True
    else:
        # Тимчасова плашка, поки фоновий потік викачує дані з Telegram (триває кілька секунд)
        st.warning("⏳ Застосунок підключається та створює базу даних. Повідомлення з'являться протягом 5-10 секунд, зачекайте будь ласка...")
        # Примусове оновлення сторінки через 3 секунди, щоб перевірити готовність
        st.fragment(run_every=3)(lambda: st.rerun())()

if st.button("🧹 Очистити мою стрічку"):
    st.session_state.msg_store = []
    st.rerun()

st.write("---")

# --- ВІДОБРАЖЕННЯ СТРІЧКИ (Оновлення кожні 2 секунди) ---
@st.fragment(run_every=2)
def display_feed():
    current_queue = st.session_state.user_queue
    has_new = False
    
    # Вичитуємо нові повідомлення, якщо вони надійшли, поки користувач дивився на екран
    while not current_queue.empty():
        try:
            msg = current_queue.get_nowait()
            if msg not in st.session_state.msg_store:
                st.session_state.msg_store.append(msg)
                has_new = True
        except queue.Empty:
            break
            
    if not st.session_state.msg_store:
        st.info("📭 У стрічці немає повідомлень. Очікуємо нові публікації...")
        return

    # Виводимо повідомлення (нові зверху)
    for msg in reversed(st.session_state.msg_store):
        st.info(msg)

if "initial_load_done" in st.session_state:
    display_feed()
