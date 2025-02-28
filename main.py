import json
import random
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import logging

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
MAX_STEPS = random.randint(7, 10)
EVENTS_FILE = 'events.json'
TOKEN = ''  # Замените на ваш реальный токен

# Загрузка событий
with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
    events_data = json.load(f)


class GameState:
    def __init__(self):
        self.user_states = {}

    def init_user(self, user_id):
        self.user_states[user_id] = {
            'hp': 5,
            'step': 0,
            'message_history': [],
            'last_played': datetime.now().strftime('%Y-%m-%d')
        }

    def delete_progress(self, user_id):
        if user_id in self.user_states:
            del self.user_states[user_id]


game_state = GameState()


async def delete_messages(update: Update, context: CallbackContext, user_id):
    """
    Удаляет все сообщения пользователя, которые бот сохранил в message_history.
    """
    if user_id in game_state.user_states:
        for msg_id in game_state.user_states[user_id]['message_history']:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=msg_id
                )
            except Exception as e:
                logger.error(f"Error deleting message: {e}")
        game_state.user_states[user_id]['message_history'] = []


def get_promo_code():
    """
    Возвращает промокод из файла promos.txt и удаляет его.
    Если промокоды закончились или файла нет, возвращает None.
    """
    try:
        with open('promos.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if not lines:
            return None  # Промокоды закончились
        promo = lines[0].strip()
        # Записываем оставшиеся промокоды обратно в файл
        with open('promos.txt', 'w', encoding='utf-8') as f:
            f.writelines(lines[1:])
        return promo
    except FileNotFoundError:
        return None


async def start(update: Update, context: CallbackContext):
    """
    Старт игры: приветственное сообщение, инициализация состояния игрока.
    """
    user_id = update.effective_user.id
    await delete_messages(update, context, user_id)

    game_state.init_user(user_id)

    msg = await update.message.reply_text(
        "🔥 Добро пожаловать в Лабиринт Смерти!\n"
        "Выберите путь:",
        reply_markup=ReplyKeyboardMarkup([['⬅️ Лево', '➡️ Право']], one_time_keyboard=True)
    )
    game_state.user_states[user_id]['message_history'].append(msg.message_id)


async def handle_choice(update: Update, context: CallbackContext):
    """
    Обработчик выбора (лево/право) на каждом шаге.
    """
    user_id = update.effective_user.id
    state = game_state.user_states.get(user_id)

    # Если состояние отсутствует — начинаем игру заново
    if not state:
        await start(update, context)
        return

    # Увеличиваем счётчик шагов
    state['step'] += 1
    is_final = state['step'] >= MAX_STEPS

    # Если финал, выбираем среди boss/exit, иначе — среди остальных
    if is_final:
        possible_events = [e for e in events_data['events'] if e['type'] in ('boss', 'exit')]
    else:
        possible_events = [e for e in events_data['events'] if e['type'] not in ('boss', 'exit')]

    if not possible_events:
        # На случай, если events.json как-то пуст или не содержит нужных событий
        await update.message.reply_text("Нет доступных событий. Проверьте файл events.json.")
        return

    event = random.choice(possible_events)

    # Обработка эффектов
    if event['type'] in ('battle', 'trap'):
        state['hp'] -= 1
    elif event['type'] in ('rest', 'treasure'):
        state['hp'] += 1
    elif event['type'] == 'miniboss':
        state['hp'] -= 2
    elif event['type'] == 'boss':
        state['hp'] -= 3
    # Другие типы — без изменений

    # Текст сообщения
    text_message = (
        f"🕳 Шаг {state['step']}\n\n"
        f"{event['story']}\n\n"
        f"{event['description']}\n\n"
        f"❤️ Здоровье: {state['hp']}"
    )

    # Проверяем, есть ли в событии изображение
    if "image" in event and event["image"]:
        # Путь к файлу
        image_path = os.path.join("images", event["image"])
        if os.path.exists(image_path):
            # Отправляем фото с подписью
            msg = await update.message.reply_photo(
                photo=open(image_path, 'rb'),
                caption=text_message,
                reply_markup=ReplyKeyboardMarkup(
                    ([['⬅️ Лево', '➡️ Право']] if not is_final else [['🔄 Начать заново']]),
                    one_time_keyboard=True
                )
            )
        else:
            # Если файла нет, шлём обычное сообщение
            msg = await update.message.reply_text(
                text_message,
                reply_markup=ReplyKeyboardMarkup(
                    ([['⬅️ Лево', '➡️ Право']] if not is_final else [['🔄 Начать заново']]),
                    one_time_keyboard=True
                )
            )
    else:
        # Если нет поля image — простое текстовое сообщение
        msg = await update.message.reply_text(
            text_message,
            reply_markup=ReplyKeyboardMarkup(
                ([['⬅️ Лево', '➡️ Право']] if not is_final else [['🔄 Начать заново']]),
                one_time_keyboard=True
            )
        )

    # Сохраняем id отправленного сообщения
    game_state.user_states[user_id]['message_history'].append(msg.message_id)

    # Проверка условий конца игры
    if state['hp'] <= 0 or is_final:
        # Удаляем все сообщения
        await delete_messages(update, context, user_id)
        # Сохраняем HP перед удалением прогресса (иначе state пропадёт)
        hp_final = state['hp']
        # Удаляем прогресс игрока
        game_state.delete_progress(user_id)

        if hp_final <= 0:
            # Проигрыш
            result_text = "💀 Вы пали в бою!\nХотите попробовать снова?"
        else:
            # Выигрыш
            result_text = "🎉 Вы достигли выхода!\n"

            # Пытаемся выдать промокод
            promo = get_promo_code()
            if promo:
                result_text += f"Поздравляю, вы победили! Вот ваш промокод:\n{promo}\n\n"
            else:
                result_text += "Промокоды закончились.\n\n"

            result_text += "Хотите попробовать снова?"

        final_msg = await update.message.reply_text(
            result_text,
            reply_markup=ReplyKeyboardMarkup([['🔄 Начать заново']], one_time_keyboard=True)
        )
        # Запоминаем, чтобы также можно было снести, если понадобится
        game_state.user_states[user_id] = {'message_history': [final_msg.message_id]}


def main():
    app = Application.builder().token(TOKEN).build()

    # Команда /start — начало игры
    app.add_handler(CommandHandler("start", start))
    # Любое текстовое сообщение, не являющееся командой — выбор пути
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice))

    # Запуск бота
    app.run_polling()


if __name__ == '__main__':
    main()
