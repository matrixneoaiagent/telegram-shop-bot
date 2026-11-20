"""Bot entrypoint."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from dotenv import load_dotenv

from .config import Settings
from .db import Database
from .handlers import admin, catalog

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="shop", description="Browse the catalog"),
    BotCommand(command="track", description="Track an order"),
    BotCommand(command="orders", description="My recent orders"),
    BotCommand(command="cancel", description="Cancel checkout"),
    BotCommand(command="help", description="How ordering works"),
]


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    db = Database(settings.db_path)
    await db.connect()
    await db.init()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["db"] = db
    dispatcher["settings"] = settings
    # Admin router first so admin commands are never swallowed by an open
    # customer checkout state.
    dispatcher.include_router(admin.build_admin_router(settings.admin_ids))
    dispatcher.include_router(catalog.router)

    logger.info("Starting shop bot for %s (db=%s)", settings.shop_name, settings.db_path)
    try:
        try:
            await bot.set_my_commands(COMMANDS)
        except TelegramAPIError:
            logger.warning("Could not set bot commands; continuing")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
        await db.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
