import json
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes,CommandHandler,CallbackQueryHandler
from telegram import ChatPermissions
from dotenv import load_dotenv
import random
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
captcha = os.getenv("CAPTCHA", "False").lower() == "true"
timezone = timedelta(hours=(int(os.getenv("TIMEZONE", 0))))
captcha_storage = {}

ollama = Client(host='http://localhost:11434')
OLLAMA_MODEL = "llama3.1:8b"  # или "mistral", "deepseek-llm" и т.д.
TARGET_SITES = ["https://abiturient.ru"]  # Список сайтов для поиска
MAX_PAGES_TO_SEARCH = 100000  # Максимальное количество страниц для сканирования
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8181")  # Адрес вашего SearxNG




# Чтение  слов и приветсвенных сообщений
with open('./banword.txt', 'r', encoding='utf-8') as file:
    forbidden_words = [word.strip().lower() for word in file if word.strip()]

with open("channels.json", "r", encoding="utf-8") as f:
    channels = json.load(f)

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
    #if not update.message or not update.message.text:
    #    return
    message = update.message or update.edited_message
    if not message or not message.text:
        return

    user = message.from_user
    message_text = message.text.lower()
    chat_id = str(message.chat_id)
    try:
        censor = channels[chat_id]["censor"]
    except:
        censor = "True"
    if censor == "True" and  any(word in message_text.split() for word in forbidden_words):
        try:
            await message.delete()
            try:
                ban_minutes = int(channels[chat_id]["ban_duration"])
                ban_duration = timedelta(minutes=ban_minutes)
                print(ban_duration)
            except:
                pass
            if  not ban_duration: return # в теории логчно что сообщение мы удалили и раз не баним то нечего с сообщением че то делать 
            
            if  ban_minutes>= 60:
                hours = ban_minutes // 60
                mins = ban_minutes % 60
                duration = f"{hours} час{'а' if 2 <= hours % 10 <= 4 and (hours % 100 < 10 or hours % 100 > 20) else 'ов'}" + (f" {mins} мин" if mins else "")
            else:
                duration = f"{ban_minutes} минут{'у' if ban_minutes == 1 else ('ы' if 2 <= ban_minutes % 10 <= 4 and (ban_minutes % 100 < 10 or ban_minutes % 100 > 20) else '')}"

            permissions = ChatPermissions(
                can_send_messages=False,  
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
            )
            restrict_duration = ban_duration
            until_date = datetime.now() + restrict_duration - timezone
            
            await context.bot.restrict_chat_member(
                chat_id=message.chat_id,
                user_id=user.id,
                permissions=permissions,
                until_date=until_date
            )
            
            warning = (
                f"⚠️ Пользователь {user.first_name} "
                f"ограничен в отправке сообщений на {duration} "
            )
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=warning
            )
        except Exception as error:
            print(f'Ошибка: {error}')
        

    try:
        
        llm = channels[chat_id]["llm"]
        print(channels[chat_id]["llm"])
    except:
        llm = "False"


    if llm == "True" and  "?" in message.text and not await is_admin(update, context):
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


def generate_captcha():
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    operation = random.choice(["+", "-", "*"])
    
    if operation == "+":
        answer = a + b
    elif operation == "-":
        answer = a - b
    else:
        answer = a * b
    
    question = f"Решите капчу: {a} {operation} {b} = ?"
    wrong_answers = [answer + random.randint(1, 3), answer - random.randint(1, 3)]
    options = [answer] + wrong_answers
    random.shuffle(options)
    return question, options, str(answer)

async def send_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    try:
        captcha = (channels[chat_id]['captcha'])
    except:
        captcha = "True"
    if channels[chat_id]["captcha"] != "True": # проверка нужна ли в канале каптча
        return

    new_member = update.message.new_chat_members[0]
    user_id = update.effective_user.id
    permissions = ChatPermissions(
                    can_send_messages=False,  
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False,
                )
    await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=permissions,
        )
    if chat_id in channels:
        welcome_data = channels[chat_id]
        welcome_text = (
            f" {new_member.mention_html()}, {welcome_data['welcome_text']}\n\n"
            " **Решите капчу для доступа:**"
        )
    else:
        welcome_text = f"{new_member.mention_html()}, добро пожаловать! Решите капчу:"
    
    # Генерируем капчу
    question, options, correct_answer = generate_captcha()
    captcha_storage[new_member.id] = correct_answer
    
    # Создаём кнопки с вариантами
    keyboard = [
        [InlineKeyboardButton(str(option), callback_data=str(option))]
        for option in options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{welcome_text}\n\n{question}",
        reply_markup=reply_markup,
        parse_mode="HTML",
    )

    
async def handle_captcha_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_answer = query.data
    chat_id = query.message.chat_id   
    if user_id in captcha_storage and user_answer == captcha_storage[user_id]:
        await query.answer("Верно! Доступ разрешён.")
        await query.delete_message()
        del captcha_storage[user_id]
        permissions = ChatPermissions(
    can_send_messages=True,          
    can_send_polls=False,           
    can_send_other_messages=True, 
    can_add_web_page_previews=False, 
    can_change_info=False,           
    can_invite_users=False,         
    can_pin_messages=False,        
)
        await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=permissions,
        )
    else:
        await query.answer("Неверно! Попробуйте ещё раз.")
def main():
    application = Application.builder().token(bot_token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, send_captcha))
    application.add_handler(CallbackQueryHandler(handle_captcha_response))
    application.run_polling()

if __name__ == '__main__':
    main()
