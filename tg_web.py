import asyncio
import threading
import queue
import re  # Додаємо бібліотеку для роботи з регулярними виразами
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
st.title(" Збірка Всього По троху")

if "TG_SESSION" in st.secrets:
    SESSION_DATA = StringSession(st.secrets["TG_SESSION"])
else:
    st.error("Помилка: Не знайдено секрет TG_SESSION в налаштуваннях Streamlit Cloud!")
    st.stop()

@st.cache_resource
def get_message_queue():
    return queue.Queue()

if "msg_store" not in st.session_state:
    st.session_state.msg_store = ["🔄 Сервер запущено. почекай це перша версія. Київ тоже не за день побудували..."]

msg_queue = get_message_queue()

# --- ФУНКЦІЯ ОЧИЩЕННЯ ТЕКСТУ ВІД ПОСИЛАНЬ ---
def clean_text(text):
    if not text:
        return ""
    # 1. Видаляємо посилання типу http:// або https://
    text = re.sub(r'https?://\S+', '', text)
    # 2. Видаляємо внутрішні посилання Telegram типу t.me/... або tg://...
    text = re.sub(r'(t\.me|tg://)\S+', '', text)
    # 3. Видаляємо юзернейми та згадки каналів через @ (наприклад, @username)
    text = re.sub(r'@\w+', '', text)
    # 4. Прибираємо зайві пробіли та порожні рядки, які залишилися після видалення
    text = re.sub(r'\n\s*\n+', '\n', text).strip()
    return text

@st.cache_resource
def start_telegram_worker():
    client = TelegramClient(SESSION_DATA, API_ID, API_HASH)

    @client.on(events.NewMessage(chats=TARGET_CHATS))
    async def handle_new_message(event):
        try:
            sender = await event.get_sender()
            sender_name = getattr(sender, 'title', getattr(sender, 'first_name', 'Канал'))
        except Exception:
            sender_name = "Канал"
            
        # Очищаємо текст повідомлення від будь-яких посилань
        cleaned_message = clean_text(event.text)
        
        # Якщо після очищення в пості взагалі нічого не залишилося, не додаємо його
        if not cleaned_message:
            return
            
        full_text = f"**👤 Від:** {sender_name}\n\n💬 {cleaned_message}"
        msg_queue.put(full_text)

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client.start()
        loop.run_until_complete(client.get_dialogs())
        loop.run_until_complete(client.run_until_disconnected())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    return client

start_telegram_worker()

if st.button("🧹 Очистити стрічку"):
    st.session_state.msg_store = ["🧹 Стрічку очищено. А тепер ще трішки зачейкай .Якщо щось буде воно покаже ( ну по ідеї повинно..."]
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

