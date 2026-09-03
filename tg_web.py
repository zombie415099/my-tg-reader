import asyncio
import threading
import queue
import streamlit as st
from telethon import TelegramClient, events

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
st.title("📥 ТА ЙОБАНА РОТ")

# 1. Кешуємо потокобезпечну чергу
@st.cache_resource
def get_message_queue():
    return queue.Queue()

# 2. Глобальний локальний список повідомлень сесії
if "msg_store" not in st.session_state:
    st.session_state.msg_store = ["🔄 РАБОТАЙ. Очікування нових постів..."]

msg_queue = get_message_queue()

# 3. Фоновий воркер з виправленою ініціалізацією сутностей Telegram
@st.cache_resource
def start_telegram_worker():
    client = TelegramClient('my_telegram_session', API_ID, API_HASH)

    # Використовуємо вбудований фільтр `chats=TARGET_CHATS`. Це змушує
    # Telethon автоматично валідувати ID на рівні самого Telegram API.
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
        
        client.start()
        
        # КРИТИЧНО ВАЖЛИВО: завантажуємо діалоги акаунта в пам'ять Telethon.
        # Без цього бібліотека "наосліп" не бачить подій за цифровими ID.
        loop.run_until_complete(client.get_dialogs())
        
        loop.run_until_complete(client.run_until_disconnected())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

# Запуск фонового процесу читання Telegram
start_telegram_worker()

# 4. Елементи керування інтерфейсу
if st.button("🧹 Очистити стрічку"):
    st.session_state.msg_store = ["🧹 Стрічку очищено. Очікування нових повідомлень..."]
    st.rerun()

st.write("---")

# 5. Динамічний фрагмент зчитування черги (Оновлюється кожні 2 секунди)
@st.fragment(run_every=2)
def display_feed():
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

display_feed()
