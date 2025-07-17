# Telegram бот для фильтрации чата

Этот бот предназначается для модерации чатов в Telegram. Он автоматически удаляет матерные слова. Изначально код и словарь взяты у [Алексея](https://github.com/FilimonovAlexey/anti-spam-telegram-bot)

## Структура проекта
- anti_swear_telegram_bot.py - файл с логикой работы бота
- banword.txt - хранит в себе список запрещенных слов

## Начало работы
Для запуска бота создайте в корневой папке файл с названием `.env` и вставьте в него токен своего бота.

Установите через pip библиотеку python-telegram-bot 

`pip install python-telegram-bot` 

Запустите бота через сиситемный интерпретатор

`python anti_swear_telegram_bot.py`
