from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from redis.asyncio import Redis

from .config import Settings, get_settings
from .crypto import Vault
from .login import LoginManager
from .db.session import init_db, make_engine, make_sessionmaker
from .handlers import admin, fallback, login, menu, start, subscription
from . import texts as T
from .middlewares.ensure_user import EnsureUserMiddleware
from .middlewares.throttle import ThrottleMiddleware
from .tasks import expiry_loop
from .worker.supervisor import Supervisor

log = logging.getLogger("selfbot")


def build(settings: Settings):
    engine = make_engine(settings.database_url)
    db = make_sessionmaker(engine)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    vault = Vault(settings.encryption_secret)
    logins = LoginManager(bot, db, redis, settings, vault)
    supervisor = Supervisor(bot, db, settings, vault)
    dp = Dispatcher(db=db, redis=redis, settings=settings, logins=logins)

    # فقط چت خصوصی
    dp.message.filter(F.chat.type == "private")
    dp.callback_query.filter(F.message.chat.type == "private")

    dp.message.outer_middleware(ThrottleMiddleware())
    dp.callback_query.outer_middleware(ThrottleMiddleware())
    dp.message.outer_middleware(EnsureUserMiddleware())
    dp.callback_query.outer_middleware(EnsureUserMiddleware())

    # ترتیب مهمه: fallback همیشه آخره
    dp.include_routers(
        admin.router, start.router, login.router, subscription.router, menu.router, fallback.router
    )

    @dp.error()
    async def on_error(event: ErrorEvent) -> bool:
        log.error("unhandled error", exc_info=event.exception)
        cq = event.update.callback_query
        if cq is not None:
            try:
                await cq.answer(T.ERROR_RETRY, show_alert=True)
            except Exception:
                pass
        return True

    tasks: list[asyncio.Task] = []

    async def on_startup(bot: Bot) -> None:
        await init_db(engine, db)
        if settings.base_url:
            await bot.set_webhook(
                url=f"{settings.base_url}/webhook",
                secret_token=settings.webhook_secret,
                allowed_updates=dp.resolve_used_update_types(),
            )
            log.info("webhook set: %s/webhook", settings.base_url)
        else:
            await bot.delete_webhook()
            log.info("no public URL: running in polling mode")
        tasks.append(asyncio.create_task(expiry_loop(bot, db, settings)))
        if settings.run_worker:
            tasks.append(asyncio.create_task(supervisor.run()))

    async def on_shutdown(bot: Bot) -> None:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await supervisor.stop()
        await logins.close_all()
        await redis.aclose()
        await engine.dispose()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return bot, dp


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    bot, dp = build(settings)

    if settings.base_url:
        app = web.Application()

        async def health(_: web.Request) -> web.Response:
            return web.json_response({"ok": True})

        app.router.add_get("/health", health)
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret).register(
            app, path="/webhook"
        )
        setup_application(app, dp, bot=bot)
        web.run_app(app, host="0.0.0.0", port=settings.port)
    else:
        asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
