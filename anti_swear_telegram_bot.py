import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram import ChatPermissions
from dotenv import load_dotenv
import json
import re 
from ollama import Client  # Добавляем клиент Ollama
import aiohttp
from bs4 import BeautifulSoup
with open('knowledge_base.json', 'r', encoding='utf-8') as f:
    knowledge_base = json.load(f)

load_dotenv()

# Конфигурация
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
banning = os.getenv("BANNING", "False").lower() == "true"
ban_minutes = int(os.getenv("BAN_DURATION", 0))
timezone = timedelta(hours=(int(os.getenv("TIMEZONE", 0))))
ban_duration = timedelta(minutes=ban_minutes) if ban_minutes > 0 else None

# Ollama клиент
ollama = Client(host='http://localhost:11434')
OLLAMA_MODEL = "llama3.1:8b"  # или "mistral", "deepseek-llm" и т.д.
TARGET_SITES = ["https://abiturient.ru"]  # Список сайтов для поиска
MAX_PAGES_TO_SEARCH = 100000  # Максимальное количество страниц для сканирования
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8181")  # Адрес вашего SearxNG
# Чтение запрещенных слов
with open('./banword.txt', 'r', encoding='utf-8') as file:
    forbidden_words = [word.strip().lower() for word in file if word.strip()]


async def fetch_full_text(session, url):
    """Скачивает и чистит текст со страницы"""
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Удалим скрипты/стили
                for tag in soup(['script', 'style']):
                    tag.decompose()
                
                text = soup.get_text(separator='\n')
                clean_text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())
                return clean_text
    except Exception as e:
        print(f"Ошибка при загрузке контента {url}: {e}")
    return ""



async def searx_search(query: str) -> tuple[str, str]:
    """Ищет информацию через SearxNG и парсит полную страницу"""
    try:
        params = {
            "q": f"site:abiturient.ru {query}",
            "format": "json",
            "language": "ru"
        }
        headers = {"Accept": "application/json"}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{SEARXNG_URL}/search", params=params, headers=headers, timeout=10
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"SearxNG результаты: {data}")

                    filtered_results = [
                        r for r in data.get('results', []) if 'abiturient.ru' in r['url']
                    ]
                    if filtered_results:
                        first = filtered_results[0]
                        url = first['url'].split('?')[0]

                        full_text = await fetch_full_text(session, url)
                        return full_text, url
    except Exception as e:
        print(f"Ошибка SearxNG: {e}")
    return "", ""





async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, является ли пользователь админом группы."""
    if not update.message or not update.message.chat:
        return False
    
    chat_id = update.message.chat.id
    user_id = update.message.from_user.id
    
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        return any(admin.user.id == user_id for admin in admins)
    except Exception as e:
        print(f"Ошибка проверки админки: {e}")
        return False

async def ask_ollama(question: str) -> str:
    """Запрашивает ответ у локальной LLM через Ollama."""
    try:
        response = ollama.generate(
            model=OLLAMA_MODEL,
            prompt=f"Ответь студенту, не выдумывай, говори только по известным данным и не выдавай что ты ИИ, просто выдай ответ,если не знаешь что сказать просто скажи, что ответ по следующей ссылке, ссылки писать не надо ее будет им видно, не говори что ты чего то не знаешь: {question}",
            stream=False
        )
        return response['response']
    except Exception as e:
        print(f"Ошибка Ollama: {e}")
        return "Извините, не могу обработать запрос."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.edited_message
    if not message or not message.text:
        return

    user = message.from_user
    message_text = message.text.lower()
    print(f"Сообщение от {user.first_name}: {message_text}")

    # Проверка на запрещённые слова
    if any(word in message_text.split() for word in forbidden_words):
        await handle_ban(update, context, user, message)
        return

    # Сначала проверяем базу знаний
    for question in knowledge_base['questions']:
        for pattern in question['patterns']:
            if re.search(pattern, message_text, re.IGNORECASE):
                await message.reply_text(question['answer'])
                return

    # Если есть "?" и пользователь не админ — спрашиваем у LLM
    if "?" in message.text and not await is_admin(update, context):
        # 1. Поиск через SearxNG
        search_result, source_url = await searx_search(message.text)
        
        if search_result:
            # 2. Перефразирование через Ollama
            answer = await ask_ollama(
                f"Дай краткий ответ на вопрос '{message.text}' "
                f"на основе этого текста:\n{search_result[:2000]}"
            )
            
            # Формируем сообщение с ссылкой
            response_text = f"🔍 Ответ:\n{answer}\n\n"
            if source_url:
                response_text += f"_[Источник]({source_url})_"
            
            await message.reply_text(
                response_text,
               # parse_mode="Markdown",
                disable_web_page_preview=True
            )
        else:
            # 3. Если поиск не дал результатов
            #llm_response = await ask_ollama(message.text)
            
            #await message.reply_text(f"💡 Ответ:\n{llm_response}")    
            pass



async def handle_ban(update: Update, context: ContextTypes.DEFAULT_TYPE, user, message):
    """Обработка бана/мута за запрещённые слова."""
    try:
        await message.delete()
        if not ban_duration:
            return

        duration_str = format_duration(ban_minutes)
        until_date = datetime.now() + ban_duration - timezone

        if banning:
            await context.bot.ban_chat_member(
                chat_id=message.chat_id,
                user_id=user.id,
                until_date=until_date
            )
            warning = f"🚫 Пользователь {user.first_name} забанен на {duration_str}!"
        else:
            permissions = ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
            await context.bot.restrict_chat_member(
                chat_id=message.chat_id,
                user_id=user.id,
                permissions=permissions,
                until_date=until_date
            )
            warning = f"🔇 Пользователь {user.first_name} ограничен на {duration_str}"

        await context.bot.send_message(chat_id=message.chat_id, text=warning)
    except Exception as error:
        print(f'Ошибка при бане: {error}')

def format_duration(minutes: int) -> str:
    """Форматирует длительность бана в читаемый вид."""
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours} час{'а' if 2 <= hours % 10 <= 4 else 'ов'}" + (f" {mins} мин" if mins else "")
    return f"{minutes} минут{'у' if minutes == 1 else ('ы' if 2 <= minutes % 10 <= 4 else '')}"

def main():
    application = Application.builder().token(bot_token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == '__main__':
    main()
