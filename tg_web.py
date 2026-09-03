import asyncio
import threading
import queue
import streamlit as st
from telethon import TelegramClient, events

# =====================================================================
# НАЛАШТУВАННЯ ЗАСТОСУНКУ (Ваші оновлені 9 чатів)
# =====================================================================
API_ID = 33419246
API_HASH = 'c84604c332b20c91eb9be6d01d4bd1ae'

TARGET_CHATS = [  
    -1002486466109, -1001206439755, -1001681084215,
    -1001855211672, -1001745595323, -1002060414600,
    -1002783917373, -1001777491812, -1001823047630,
]
# =====================================================================

st.set_page_config(page_title="TG Web Reader", page_icon="💬", layout="centered")
st.title("📥 Де ЩО ЛЕТИТЬ")

# 1. Кешуємо чергу для обміну даними між потоками
@st.cache_resource
def get_message_queue():
    return queue.Queue()

# 2. Сховище повідомлень для поточного користувача
if "msg_store" not in st.session_state:
    st.session_state.msg_store = ["🔄 Сервер запущено. Очікування нових постів..."]

msg_queue = get_message_queue()

# 3. Фоновий клієнт Telegram (працює завжди в 1 екземплярі)
@st.cache_resource
def start_telegram_worker():
    client = TelegramClient('my_telegram_session', API_ID, API_HASH)

    @client.on(events.NewMessage)
    async def handle_new_message(event):
        if event.chat_id in TARGET_CHATS:
            sender = await event.get_sender()
            sender_name = getattr(sender, 'title', getattr(sender, 'first_name', 'Канал'))
            full_text = f"**👤 Від:** {sender_name}\n\n💬 {event.text}"
            
            # Кладемо повідомлення в чергу
            msg_queue.put(full_text)

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client.start()
        loop.run_until_complete(client.run_until_disconnected())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

# Запуск фонового процесу
start_telegram_worker()

# 4. Кнопка очищення стрічки
if st.button("🧹 Очистити стрічку"):
    st.session_state.msg_store = ["🧹 Стрічку очищено. В очікуванні нових повідомлень..."]
    st.rerun()

st.write("---")

# 5. ДИНАМІЧНИЙ ФРАГМЕНТ (Оновлюється автоматично кожні 2 секунди)
@st.fragment(run_every=2)
def display_feed():
    # Вигрібаємо ВСІ нові повідомлення з черги, які встигли прийти
    has_updates = False
    while not msg_queue.empty():
        try:
            msg = msg_queue.get_nowait()
            st.session_state.msg_store.append(msg)
            has_updates = True
        except queue.Empty:
            break
            
    # Виводимо стрічку повідомлень на екран
    for msg in reversed(st.session_state.msg_store):
        st.info(msg)

# Запускаємо відображення нашої стрічки
display_feed()
