import asyncio
import threading
import queue
import re
import datetime
from datetime import timezone
import streamlit as st
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# Спроба імпортувати zoneinfo для точного визначення київського часу з урахуванням літа/зими
try:
    from zoneinfo import ZoneInfo
    KYIV_TZ = ZoneInfo("Europe/Kyiv")
except Exception:
    # Надійний бекап: якщо zoneinfo не підтримується, ставимо фіксований київський літній час UTC+3
    KYIV_TZ = timezone(datetime.timedelta(hours=3))

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

# Скільки годин зберігати повідомлення в пам'яті сервера (щоб не переповнювався)
MAX_HISTORY_HOURS = 3 
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
        "active_queues": set(),    # Усі активні черги користувачів
        "history_buffer": [],      # Список кортежів: (timestamp, formatted_text)
        "history_ready": False     # Прапор готовності історії
    }

global_state = get_global_state()

# --- РОЗУМНА ЧЕРГА З АВТООЧИЩЕННЯМ ПРИ ЗАКРИТТІ ВКЛАДКИ ---
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

# --- ІНІЦІАЛІЗАЦІЯ ДЛЯ КОНКРЕТНОЇ ВКЛАДКИ КОРИСТУВАЧА ---
if "msg_store" not in st.session_state:
    st.session_state.msg_store = []

if "user_queue" not in st.session_state:
    st.session_state.user_queue = AutoCleanupQueue(global_state["active_queues"])

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
        
    msg_date = event_or_message.date
    if msg_date:
        # ПРИМУСОВО переводимо час Telegram в часовий пояс Києва
        local_time = msg_date.astimezone(KYIV_TZ)
        time_str = local_time.strftime("%H:%M:%S")
    else:
        # Для нових повідомлень, якщо немає дати, беремо поточний час у Києві
        time_str = datetime.datetime.now(KYIV_TZ).strftime("%H:%M:%S")
        
    return f"👤 **Від:** {sender_name} | 🕒 *{time_str}*\n\n💬 {cleaned_message}"

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
        full_text = await process_and_enqueue(event)
        if full_text:
            now = datetime.datetime.now(timezone.utc)
            global_state["history_buffer"].append((now, full_text))
            clean_old_server_history()
            
            for q in list(global_state["active_queues"]):
                try:
                    q.put(full_text)
                except Exception:
                    continue

    async def preload_history():
        time_limit = datetime.datetime.now(timezone.utc) - datetime.timedelta(minutes=30)
        all_messages = []
        
        for chat_id in TARGET_CHATS:
            try:
                async for message in client.iter_messages(chat_id, limit=25, offset_date=time_limit, reverse=True):
                    if message.date and message.date >= time_limit:
                        all_messages.append(message)
            except Exception:
                continue
                
        all_messages.sort(key=lambda m: m.date or time_limit)
        
        for msg in all_messages:
            formatted = await process_and_enqueue(msg)
            msg_date = msg.date or time_limit
            if formatted:
                if not any(item[1] == formatted for item in global_state["history_buffer"]):
                    global_state["history_buffer"].append((msg_date, formatted))
                    
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
        st.warning("⏳ Застосунок підключається та створює базу даних. Повідомлення з'являться протягом декількох секунд...")
        st.fragment(run_every=2)(lambda: st.rerun())()

if st.button("🧹 Очистити мою стрічку"):
    st.session_state.msg_store = []
    st.rerun()

st.write("---")

# --- ВІДОБРАЖЕННЯ СТРІЧКИ ---
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
            
    if not st.session_state.msg_store:
        st.info("📭 У стрічці немає повідомлень. Очікуємо нові публікації...")
        return

    for msg in reversed(st.session_state.msg_store):
        st.info(msg)

if "initial_load_done" in st.session_state:
    display_feed()
