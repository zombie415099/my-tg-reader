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
st.title("📥 Стрічка обраних повідомлень")

# 1. Створюємо глобальну чергу для обміну даними між потоками (кешуємо її)
@st.cache_resource
def get_message_queue():
    return queue.Queue()

# 2. Глобальне сховище для накопичених повідомлень в рамках цієї сесії користувача
if "msg_store" not in st.session_state:
    st.session_state.msg_store = ["🔄 Сервер запущено. В очікуванні нових постів..."]

msg_queue = get_message_queue()

# 3. Ініціалізація та запуск клієнта Telegram в окремому потоці (лише 1 раз)
@st.cache_resource
def start_telegram_worker():
    client = TelegramClient('my_telegram_session', API_ID, API_HASH)

    @client.on(events.NewMessage)
    async def handle_new_message(event):
        if event.chat_id in TARGET_CHATS:
            sender = await event.get_sender()
            sender_name = getattr(sender, 'title', getattr(sender, 'first_name', 'Канал'))
            full_text = f"**👤 Від:** {sender_name}\n\n💬 {event.text}"
            
            # БЕЗПЕЧНО додаємо в чергу замість st.session_state
            msg_queue.put(full_text)

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client.start()
        # Дозволяє коректно обробляти запити всередині потоку
        loop.run_until_complete(client.run_until_disconnected())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

# Запускаємо фоновий потік процесу Telegram
start_telegram_worker()

# 4. Перевіряємо чергу: якщо фоновий потік щось надіслав — переміщуємо в сесію Streamlit
new_messages_received = False
while not msg_queue.empty():
    try:
        msg = msg_queue.get_nowait()
        st.session_state.msg_store.append(msg)
        new_messages_received = True
    except queue.Empty:
        break

# 5. Кнопка очищення
if st.button("🧹 Очистити стрічку"):
    st.session_state.msg_store = ["🧹 Стрічку очищено. Очікування нових повідомлень..."]
    st.rerun()

st.write("---")

# 6. Виведення повідомлень
for msg in reversed(st.session_state.msg_store):
    st.info(msg)

# 7. Автоматичне оновлення сторінки (фрагменту інтерфейсу) кожні 3 секунди
# Це замінює небезпечний st.rerun() з фонового потоку
st.fragment(run_every=3)(lambda: None)()
