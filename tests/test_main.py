import asyncio
import logging
import pytest
from types import SimpleNamespace

import main
from main import global_error_handler


def test_global_error_handler_logs_exception(caplog):
    error = RuntimeError("Test internal failure")
    context = SimpleNamespace(error=error)

    with caplog.at_level(logging.ERROR):
        asyncio.run(global_error_handler(None, context))

    assert "Unhandled exception" in caplog.text
    assert "RuntimeError: Test internal failure" in caplog.text


def test_global_error_handler_handles_missing_exception(caplog):
    context = SimpleNamespace(error=None)

    with caplog.at_level(logging.ERROR):
        asyncio.run(global_error_handler(None, context))

    assert "without exception details" in caplog.text


class FakeJobQueue:
    def __init__(self):
        self.jobs = []

    def run_repeating(self, callback, **kwargs):
        self.jobs.append((callback, kwargs))


class FakeApp:
    def __init__(self, job_queue=True):
        self.job_queue = FakeJobQueue() if job_queue else None
        self.handlers = []
        self.error_handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)

    def add_error_handler(self, handler):
        self.error_handlers.append(handler)


class FakeBuilder:
    def __init__(self, app):
        self.app = app

    def token(self, value):
        return self

    def post_init(self, callback):
        self.init_callback = callback
        return self

    def build(self):
        return self.app


def test_build_application_registers_scheduled_jobs(monkeypatch):
    fake_app = FakeApp()

    class FakeApplication:
        @staticmethod
        def builder():
            return FakeBuilder(fake_app)

    monkeypatch.setattr(main, "Application", FakeApplication)

    app = main.build_application()

    assert app.error_handlers == [main.global_error_handler]
    assert len(app.job_queue.jobs) == 2

    alert_callback, alert_config = app.job_queue.jobs[0]
    assert alert_callback is main.check_price_alerts_job
    assert alert_config == {
        "interval": 300,
        "first": 30,
        "name": "price-alert-checker",
    }

    backup_callback, backup_config = app.job_queue.jobs[1]
    assert backup_callback is main.automatic_database_backup
    assert backup_config == {
        "interval": 86400,
        "first": 60,
        "name": "automatic-database-backup",
    }


def test_build_application_requires_job_queue(monkeypatch):
    fake_app = FakeApp(job_queue=False)

    class FakeApplication:
        @staticmethod
        def builder():
            return FakeBuilder(fake_app)

    monkeypatch.setattr(main, "Application", FakeApplication)

    with pytest.raises(RuntimeError, match="JobQueue is unavailable"):
        main.build_application()


def test_post_init_syncs_telegram_command_menu(monkeypatch):
    class FakeBot:
        commands = None

        async def set_my_commands(self, commands):
            self.commands = commands

    fake_bot = FakeBot()
    fake_app = SimpleNamespace(bot=fake_bot)
    initialized = []

    async def fake_init_db():
        initialized.append(True)

    monkeypatch.setattr(main, "init_db", fake_init_db)

    asyncio.run(main.post_init(fake_app))

    assert initialized == [True]
    assert fake_bot.commands == main.BOT_COMMANDS
    assert len(fake_bot.commands) == 33
    assert len({command.command for command in fake_bot.commands}) == 33


def test_post_init_continues_if_command_menu_sync_fails(
    monkeypatch, caplog
):
    class FakeBot:
        async def set_my_commands(self, commands):
            raise RuntimeError("Telegram API unavailable")

    initialized = []

    async def fake_init_db():
        initialized.append(True)

    monkeypatch.setattr(main, "init_db", fake_init_db)

    with caplog.at_level(logging.ERROR):
        asyncio.run(
            main.post_init(SimpleNamespace(bot=FakeBot()))
        )

    assert initialized == [True]
    assert "Failed to synchronize Telegram command menu" in caplog.text
