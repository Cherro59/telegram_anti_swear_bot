import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram import ChatPermissions
from dotenv import load_dotenv

load_dotenv()

# Конфигурация
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
banning = os.getenv("BANNING", "False").lower() == "true"
ban_minutes = int(os.getenv("BAN_DURATION", 0))
timezone = timedelta(hours=(int(os.getenv("TIMEZONE", 0))))
ban_duration = timedelta(minutes=ban_minutes) if ban_minutes > 0 else None

# Чтение запрещенных слов
with open('./banword.txt', 'r', encoding='utf-8') as file:
    forbidden_words = [word.strip().lower() for word in file if word.strip()]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #if not update.message or not update.message.text:
    #    return
    message = update.message or update.edited_message
    if not message or not message.text:
        return

    user = message.from_user
    message_text = message.text.lower()
    #user = update.message.from_user

    #message_text = update.message.text.lower()
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
                
                # Применяем ограничение
                await context.bot.restrict_chat_member(
                    chat_id=message.chat_id,
                    user_id=user.id,
                    permissions=permissions,
                    until_date=until_date
                )
                
                # Отправляем уведомление

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

def main():
    application = Application.builder().token(bot_token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()

if __name__ == '__main__':
    main()
