import logging

from aiogram import Bot, Dispatcher, executor, types
from config_reader import config

API_TOKEN = config.bot_token.get_secret_value()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):

    await message.reply("Здравствуйте это бот документооборо")


@dp.message_handler()
async def echo(message: types.Message):
    await message.answer(message.text)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
# https://aiogram.ru/?p=33 - ссыль на кнопки
