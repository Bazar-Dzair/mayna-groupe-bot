# Mayna bot patch — delivery prices

Root cause of "no answer to «شحال التوصيل لوهران؟»": bot.py used `re.search` without `import re`
-> NameError on every price question, swallowed by the error handler (no reply). Also: `\\n` double
escapes, ADMIN_CHAT_ID / GEMINI_API_KEY never passed by the workflow.

Changes
- delivery_prices.json (new): 58 wilayas, aliases (Arabic/Darija/French), home + office prices. 9999 = needs admin confirmation.
- delivery.py (new): intent detection (price vs duration/companies/tracking), wilaya extraction, reply builder.
- bot.py: delivery engine runs first in handle_group_message; safe reply with retry; Conflict diagnostics; startup self-test log.
- .github/workflows/bot.yml: passes all secrets, runs syntax check + tests before starting the bot.
- tests/test_delivery.py, tests/test_real_ptb.py (new); tests/test_bot_flow.py (2 old assertions updated: price questions are now answered with the price, not by copying post 399).

Run tests:  python -m unittest discover -s tests -t .
Without python-telegram-bot installed, tests use tests/telegram_stub.py; tests/test_real_ptb.py needs the real package.

Secrets: TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, GEMINI_API_KEY (optional), GROUP_CHAT_ID (optional; used if RESTRICT_TO_GROUP=1).
