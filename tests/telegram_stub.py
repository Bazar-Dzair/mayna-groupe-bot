"""Minimal stand-in for python-telegram-bot, used ONLY when the real package is not installed.

It lets the handler logic be imported and exercised with mocks. It does NOT emulate Telegram
or PTB's real filter semantics; those must be verified by a real run of the bot.
"""
import sys
import types


def install() -> bool:
    try:
        import telegram  # noqa: F401
        return False
    except ModuleNotFoundError:
        pass

    tg = types.ModuleType("telegram")
    err = types.ModuleType("telegram.error")
    ext = types.ModuleType("telegram.ext")

    class Update:
        ALL_TYPES = ["all"]

    class TelegramError(Exception):
        pass

    class Conflict(TelegramError):
        pass

    class _F:
        def __init__(self, name):
            self.name = name

        def __and__(self, other):
            return _F(f"({self.name} & {other.name})")

        def __or__(self, other):
            return _F(f"({self.name} | {other.name})")

        def __invert__(self):
            return _F(f"~{self.name}")

        def __repr__(self):
            return self.name

    class _NS:
        pass

    filters = _NS()
    filters.COMMAND = _F("COMMAND")
    filters.TEXT = _F("TEXT")
    filters.CAPTION = _F("CAPTION")
    filters.PHOTO = _F("PHOTO")
    filters.StatusUpdate = _NS()
    filters.StatusUpdate.NEW_CHAT_MEMBERS = _F("NEW_CHAT_MEMBERS")
    filters.StatusUpdate.ALL = _F("STATUS_ALL")
    filters.Document = _NS()
    filters.Document.ALL = _F("DOCUMENT")
    filters.ChatType = _NS()
    filters.ChatType.GROUPS = _F("GROUPS")
    filters.ChatType.CHANNEL = _F("CHANNEL")

    class MessageHandler:
        def __init__(self, flt, callback):
            self.filters, self.callback = flt, callback

    class _App:
        def __init__(self):
            self.handlers, self.error_handlers, self.polling = [], [], None

        def add_handler(self, h):
            self.handlers.append(h)

        def add_error_handler(self, h):
            self.error_handlers.append(h)

        def run_polling(self, **kw):
            self.polling = kw

    class _Builder:
        def token(self, t):
            self._t = t
            return self

        def build(self):
            app = _App()
            Application.last = app
            return app

    class Application:
        last = None

        @staticmethod
        def builder():
            return _Builder()

    class ContextTypes:
        DEFAULT_TYPE = object

    tg.Update = Update
    err.TelegramError = TelegramError
    err.Conflict = Conflict
    ext.Application, ext.ContextTypes, ext.MessageHandler, ext.filters = (
        Application, ContextTypes, MessageHandler, filters,
    )
    tg.error, tg.ext = err, ext
    sys.modules.update({"telegram": tg, "telegram.error": err, "telegram.ext": ext})
    return True
