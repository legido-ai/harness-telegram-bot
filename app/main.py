"""Entrypoint: one asyncio loop running the poller, the event stream and health."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

import uvicorn
from telegram import Update
from telegram.error import Conflict, InvalidToken

from app.backends import build_backend
from app.backends.errors import HarnessError
from app.config import ConfigError, Settings
from app.health import HealthState, create_app
from app.logging import configure_logging
from app.speech.stt import SttClient
from app.speech.tts import TtsClient
from app.store import Store
from app.telegram.app import BotApp
from app.telegram.runner import Runner

POLLER_CHECK_INTERVAL = 15.0


async def _poller_watch(application, state: HealthState, stop: asyncio.Event) -> None:
    """Health must reflect the updater, not just the fact that we started it.

    A dead or conflicted poller keeps the process alive and used to look healthy.
    """

    while not stop.is_set():
        updater = getattr(application, "updater", None)
        state.poller_alive = bool(updater and updater.running)
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLLER_CHECK_INTERVAL)
        except TimeoutError:
            continue


async def _agent_watch(backend, state: HealthState, stop: asyncio.Event) -> None:
    """Kept for the opencode backend: its SSE stream is started separately."""

    while not stop.is_set():
        state.agent_ok = await backend.ping()
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLLER_CHECK_INTERVAL * 4)
        except TimeoutError:
            continue


async def run() -> int:
    settings = Settings.from_env()
    log = configure_logging(settings.log_level, settings.secrets)

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)

    store = Store(settings.db_path)
    store.migrate()
    store.prune_delivery()
    if store.bind_backend(settings.backend):
        log.warning("session bindings cleared: this database belongs to another backend")

    backend = build_backend(settings)
    state = HealthState(backend=settings.backend)
    stt = SttClient(settings)
    tts = TtsClient(settings)
    runner = Runner(settings=settings, store=store, backend=backend, tts=tts)

    bot_app = BotApp(
        settings=settings, store=store, backend=backend, runner=runner, state=state, stt=stt
    )
    runner.set_interaction_hook(bot_app.on_interaction)

    try:
        await backend.start()
    except HarnessError as exc:
        log.error("backend %s cannot start: %s", settings.backend, exc.user_message)
        store.close()
        return 78

    application = bot_app.build()
    try:
        await application.initialize()
        # post_init is not invoked by start() when the lifecycle is driven
        # manually; without it the bot has no identity and health stays degraded.
        if application.post_init is not None:
            await application.post_init(application)
        await application.start()
    except InvalidToken:
        log.critical("Telegram rejected the bot token")
        return 2

    try:
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    except Conflict:
        log.critical(
            "another process is polling this bot token (Telegram 409 Conflict); "
            "stop the other poller and restart"
        )
        await application.stop()
        return 2
    except InvalidToken:
        log.critical("Telegram rejected the bot token")
        await application.stop()
        return 2

    runner.set_messenger(bot_app.messenger)  # type: ignore[arg-type]

    stop = asyncio.Event()

    def _request_stop(*_: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_stop)

    api = create_app(settings, store, state)
    server = uvicorn.Server(
        uvicorn.Config(api, host=settings.health_host, port=settings.health_port, log_level="warning")
    )
    tasks = [
        asyncio.create_task(server.serve(), name="health"),
        asyncio.create_task(backend.background(stop, state), name="backend"),
        asyncio.create_task(_agent_watch(backend, state, stop), name="agent-watch"),
        asyncio.create_task(_poller_watch(application, state, stop), name="poller-watch"),
    ]

    log.info("bot started", extra={"event": f"health on {settings.health_host}:{settings.health_port}"})
    await stop.wait()

    state.poller_alive = False
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    await runner.stop()
    for task in tasks:
        task.cancel()
    with contextlib.suppress(Exception):
        await asyncio.gather(*tasks, return_exceptions=True)
    await backend.aclose()
    store.close()
    log.info("bot stopped")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(run()))
    except ConfigError as exc:
        logging.getLogger("bot").error("configuration error: %s", exc)
        raise SystemExit(78) from exc


if __name__ == "__main__":
    main()
