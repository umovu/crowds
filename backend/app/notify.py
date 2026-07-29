"""
Outbound admin notifications — currently Telegram.

Used to ping the operator when someone joins the waitlist, so a new sign-up
doesn't sit unnoticed. Deliberately tiny and best-effort: a failed ping must
never break the request that triggered it.

Setup (once):
  1. In Telegram, message @BotFather and send /newbot. It hands back a token.
  2. Message your new bot once (it can't message you first).
  3. Open https://api.telegram.org/bot<TOKEN>/getUpdates and copy `chat.id`.
  4. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID on the backend.

Env:
  TELEGRAM_BOT_TOKEN   from @BotFather
  TELEGRAM_CHAT_ID     your personal chat id
"""

import os

import requests

from .utils.logger import get_logger

logger = get_logger("fub.notify")


def telegram_enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and
                os.environ.get("TELEGRAM_CHAT_ID"))


def send_telegram(text: str) -> bool:
    """Send a message. Returns True if it went out; never raises."""
    if not telegram_enabled():
        logger.info("Telegram not configured — skipping ping: %s", text.split("\n")[0])
        return False
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": os.environ["TELEGRAM_CHAT_ID"],
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Telegram ping failed: %s", e)
        return False
