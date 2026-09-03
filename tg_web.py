import asyncio
import threading
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

# Ініціалізація внутрішньої пам'яті для повідомлень на веб-сторінці
if "msg_store" not in st.session_state:
    st.session_state.msg_store = ["🔄 Сервер запущено. Очікування нових постів..."]

# Конфігурація відображення сторінки
st.set_page_config(page_title="TG Web Reader", page_icon="💬", layout="centered")
st.title("📥 Стрічка обраних повідомлень")

# Кешування клієнта Telegram, щоб він не перезапускався при кожному оновленні сторінки
@st.cache_resource
def get_tg_client():
    return TelegramClient('my_telegram_session', API_ID, API_HASH)

client = get_tg_client()

@client.on(events.NewMessage)
async def handle_new_message(event):
    if event.chat_id in TARGET_CHATS:
        sender = await event.get_sender()
        sender_name = getattr(sender, 'title', getattr(sender, 'first_name', 'Канал'))
        
        # Форматуємо картку повідомлення
        full_text = f"**👤 Від:** {sender_name}\n\n💬 {event.text}"
        
        # Додаємо повідомлення на початок списку
        st.session_state.msg_store.append(full_text)
        
        # Перезавантажуємо сторінку в браузері, щоб миттєво показати новий пост
        st.rerun()

async def start_tg():
    await client.start()
    await client.run_until_disconnected()

def run_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_tg())

# Запуск фонового прослуховування Telegram в окремому потоці
if "tg_started" not in st.session_state:
    st.session_state.tg_started = True
    threading.Thread(target=run_loop, daemon=True).start()

# Кнопка для ручного очищення стрічки новин
if st.button("🧹 Очистити стрічку"):
    st.session_state.msg_store = ["🧹 Стрічку очищено. Очікування нових повідомлень..."]
    st.rerun()

st.write("---")

# Виведення повідомлень на екран (нові будуть зверху)
for msg in reversed(st.session_state.msg_store):
    st.info(msg)
