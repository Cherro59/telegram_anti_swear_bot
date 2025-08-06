import json
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, ContextTypes,CommandHandler,CallbackQueryHandler
from telegram import ChatPermissions
from dotenv import load_dotenv
import random
load_dotenv()

# Конфигурация
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
banning = os.getenv("BANNING", "False").lower() == "true"
captcha = os.getenv("CAPTCHA", "False").lower() == "true"
ban_minutes = int(os.getenv("BAN_DURATION", 0))
timezone = timedelta(hours=(int(os.getenv("TIMEZONE", 0))))
ban_duration = timedelta(minutes=ban_minutes) if ban_minutes > 0 else None
captcha_storage = {}

# Чтение  слов и приветсвенных сообщений
with open('./banword.txt', 'r', encoding='utf-8') as file:
    forbidden_words = [word.strip().lower() for word in file if word.strip()]

with open("welcome_messages.json", "r", encoding="utf-8") as f:
    welcome_messages = json.load(f)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #if not update.message or not update.message.text:
    #    return
    message = update.message or update.edited_message
    if not message or not message.text:
        return

    user = message.from_user
    message_text = message.text.lower()

    print(message_text) 
   
    if any(word in message_text.split() for word in forbidden_words):
        try:
            await message.delete()
            if  not ban_duration: return 
            
            if ban_minutes >= 60:
                hours = ban_minutes // 60
                mins = ban_minutes % 60
                duration = f"{hours} час{'а' if 2 <= hours % 10 <= 4 and (hours % 100 < 10 or hours % 100 > 20) else 'ов'}" + (f" {mins} мин" if mins else "")
            else:
                duration = f"{ban_minutes} минут{'у' if ban_minutes == 1 else ('ы' if 2 <= ban_minutes % 10 <= 4 and (ban_minutes % 100 < 10 or ban_minutes % 100 > 20) else '')}"

            if banning:
                until_date = datetime.now() + ban_duration - timezone
                

                await context.bot.ban_chat_member(
                    chat_id=message.chat_id,
                    user_id=user.id,
                    until_date=until_date
                )
                warning = f" Пользователь {user.first_name} забанен на {duration}!"
                await context.bot.send_message(
                    chat_id=message.chat_id,
                    text=warning
                )
            else:    
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
    if chat_id in welcome_messages:
        welcome_data = welcome_messages[chat_id]
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
    if captcha == True : 
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, send_captcha))
        application.add_handler(CallbackQueryHandler(handle_captcha_response))
    application.run_polling()

if __name__ == '__main__':
    main()
