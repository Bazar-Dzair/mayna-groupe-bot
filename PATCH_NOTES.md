# Mayna bot patch

Files: bot.py (replaces), matcher.py (new), tests/ (new), requirements.txt, .github/workflows/bot.yml (PROPOSED).

Run tests:  python -m unittest discover -s tests -t .
Without python-telegram-bot installed, tests use tests/telegram_stub.py (stand-in, not real Telegram).

Secrets expected: TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID (needed to forward questions), GEMINI_API_KEY (optional),
GROUP_CHAT_ID (optional; only used if RESTRICT_TO_GROUP=1).
