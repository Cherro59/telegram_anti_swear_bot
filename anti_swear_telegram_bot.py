import os
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

with open('./.env', 'r', encoding='utf-8') as file:
    bot_token = file.readline().strip()
# Чтение запрещенных слов из файла
with open('./banword.txt', 'r', encoding='utf-8') as file:
    forbidden_words = [word.strip().lower() for word in file.readlines() if word.strip()]

async def handle_message(update: Update, context):
    message_text = update.message.text.lower()
    
    # Проверка на наличие запрещенных слов
    if any(word in message_text for word in forbidden_words):
        try:
            # Удаление сообщения
            await update.message.delete()
            
            # Отправка предупреждения
        except Exception as error:
            print(f'Ошибка при удалении сообщения или отправке предупреждения: {error}')

def main():
    application = Application.builder().token(bot_token).build()
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == '__main__':
    main()
