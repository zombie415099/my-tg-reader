import asyncio
import threading
import queue
import streamlit as st
from telethon import TelegramClient, events
from telethon.sessions import StringSession  # Імпортуємо роботу з рядковими сесіями

# =====================================================================
# НАЛАШТУВАННЯ ЗАСТОСУНКУ (Ваші 9 чатів)
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
st.title("📥 Стрічка обраних повідомлень")

# Отримуємо сесію з безпечних налаштувань хостингу Streamlit
if "TG_SESSION" in st.secrets:
    SESSION_DATA = StringSession(st.secrets["TG_SESSION"])
else:
    st.error("Помилка: Не знайдено секрет TG_SESSION в налаштуваннях Streamlit Cloud!")
    st.stop()

@st.cache_resource
def get_message_queue():
    return queue.Queue()

if "msg_store" not in st.session_state:
    st.session_state.msg_store = ["🔄 Сервер запущено. Очікування нових постів..."]

msg_queue = get_message_queue()

@st.cache_resource
def start_telegram_worker():
    # Запускаємо клієнт через текстову сесію (без створення файлів .sqlite на сервері)
    client = TelegramClient(SESSION_DATA, API_ID, API_HASH)

    @client.on(events.NewMessage(chats=TARGET_CHATS))
    async def handle_new_message(event):
        try:
            sender = await event.get_sender()
            sender_name = getattr(sender, 'title', getattr(sender, 'first_name', 'Канал'))
        except Exception:
            sender_name = "Канал (Приватний/Прихований)"
            
        full_text = f"**👤 Від:** {sender_name}\n\n💬 {event.text}"
        msg_queue.put(full_text)

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Запуск тепер відбудеться миттєво, без очікування вводу даних в консоль
        client.start()
        
        loop.run_until_complete(client.get_dialogs())
        loop.run_until_complete(client.run_until_disconnected())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

# Запуск фонового процесу
start_telegram_worker()

if st.button("🧹 Очистити стрічку"):
    st.session_state.msg_store = ["🧹 Стрічку очищено. Очікування нових повідомлень..."]
    st.rerun()

st.write("---")

@st.fragment(run_every=2)
def display_feed():
    while not msg_queue.empty():
        try:
            msg = msg_queue.get_nowait()
            st.session_state.msg_store.append(msg)
        except queue.Empty:
            break
            
    for msg in reversed(st.session_state.msg_store):
        st.info(msg)

display_feed()
