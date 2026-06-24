from __future__ import annotations

import asyncio
import logging
import os

from aiogram.client.session.aiohttp import AiohttpSession

import main

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _proxy_url() -> str | None:
    for key in ("TG_PROXY_URL", "ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return None


def _build_session(proxy_url: str | None) -> AiohttpSession | None:
    if not proxy_url:
        return None
    return AiohttpSession(proxy=proxy_url)


async def run() -> None:
    proxy_url = _proxy_url()
    session = _build_session(proxy_url)

    if session is None:
        await main.run()
        return

    original_bot = main.Bot

    def bot_factory(token: str, *args, **kwargs):
        kwargs.setdefault("session", session)
        return original_bot(token, *args, **kwargs)

    main.Bot = bot_factory  # type: ignore[assignment]
    logger.info("Proxy enabled for Telegram bot: %s", proxy_url)

    try:
        await main.run()
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(run())
