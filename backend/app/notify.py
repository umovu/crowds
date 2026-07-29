"""
Outbound admin notifications — pings the operator when someone joins the
waitlist, so a new sign-up doesn't sit unnoticed.

Three channels, all optional, all best-effort. A failed ping must never break
the request that triggered it.

Discord (free, and the URL is send-only — nobody can read your alerts with it):
  Server -> channel gear -> Integrations -> Webhooks -> New Webhook -> Copy URL.
  Put it in DISCORD_WEBHOOK_URL. Leaked? Delete the webhook and make another.

ntfy (free, no account at all):
  1. Install the "ntfy" app (Android / iOS) or open https://ntfy.sh in a browser.
  2. Subscribe to a private, hard-to-guess topic name.
  3. Set NTFY_TOPIC to that same name on the backend.
  The topic name IS the secret — anyone who knows it can read your pings, so
  keep it long and random.

Telegram (alternative; needs a phone number to register an account):
  @BotFather -> /newbot -> token; message the bot once; read `chat.id` from
  https://api.telegram.org/bot<TOKEN>/getUpdates.

Env:
  DISCORD_WEBHOOK_URL  channel webhook (enables Discord)
  NTFY_TOPIC           private topic name (enables ntfy)
  NTFY_SERVER          defaults to https://ntfy.sh
  TELEGRAM_BOT_TOKEN   from @BotFather
  TELEGRAM_CHAT_ID     your personal chat id
"""

import os

import requests

from .utils.logger import get_logger

logger = get_logger("fub.notify")

_NTFY_DEFAULT_SERVER = "https://ntfy.sh"


def discord_enabled() -> bool:
    return bool(os.environ.get("DISCORD_WEBHOOK_URL"))


def ntfy_enabled() -> bool:
    return bool(os.environ.get("NTFY_TOPIC"))


def telegram_enabled() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and
                os.environ.get("TELEGRAM_CHAT_ID"))


def notify_enabled() -> bool:
    return discord_enabled() or ntfy_enabled() or telegram_enabled()


def send_discord(title: str, body: str, link: str = "") -> bool:
    """Post to a Discord channel webhook. Returns True if it went out; never raises."""
    if not discord_enabled():
        return False
    text = f"**{title}**\n{body}"
    if link:
        text += f"\n{link}"
    try:
        resp = requests.post(
            os.environ["DISCORD_WEBHOOK_URL"],
            json={"content": text, "allowed_mentions": {"parse": []}},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Discord ping failed: %s", e)
        return False


def send_ntfy(title: str, body: str, link: str = "") -> bool:
    """Push via ntfy. Returns True if it went out; never raises."""
    if not ntfy_enabled():
        return False
    server = os.environ.get("NTFY_SERVER", _NTFY_DEFAULT_SERVER).rstrip("/")
    topic = os.environ["NTFY_TOPIC"]
    # Header values must be latin-1 safe (requests encodes them that way), and
    # ntfy reads the title from a header rather than the body.
    headers = {"Title": title.encode("ascii", "replace").decode("ascii")}
    if link:
        # Makes the notification itself tappable.
        headers["Click"] = link
    try:
        resp = requests.post(f"{server}/{topic}", data=body.encode("utf-8"),
                             headers=headers, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("ntfy ping failed: %s", e)
        return False


def send_telegram(text: str) -> bool:
    """Send a Telegram message. Returns True if it went out; never raises."""
    if not telegram_enabled():
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


def send_alert(title: str, body: str, link: str = "") -> bool:
    """Ping the operator on whichever channel is configured.

    Tries every enabled channel so a misconfigured one can't silently swallow
    the alert. Returns True if at least one delivered.
    """
    if not notify_enabled():
        logger.info("No notification channel configured — skipping: %s", title)
        return False
    sent = send_discord(title, body, link)
    sent = send_ntfy(title, body, link) or sent
    if telegram_enabled():
        text = f"<b>{title}</b>\n{body}"
        if link:
            text += f'\n\n<a href="{link}">Tap to approve</a>'
        sent = send_telegram(text) or sent
    return sent
