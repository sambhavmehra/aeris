import logging
import platform
import asyncio
from typing import Optional

logger = logging.getLogger("aeris.notification_hub")

def send_desktop_notification(title: str, message: str):
    """Sends a native Windows/OS desktop notification asynchronously in a thread."""
    if platform.system() == "Windows":
        try:
            from win11toast import toast
            import threading
            # Run toast in thread to avoid blocking FastAPI/asyncio thread
            threading.Thread(target=lambda: toast(title, message), daemon=True).start()
            logger.info(f"Desktop notification dispatched: '{title}'")
        except Exception as e:
            logger.warning(f"win11toast failed: {e}. Fallback to printing.")
            print(f"\n🔔 [DESKTOP NOTIFICATION] {title}: {message}\n")
    else:
        print(f"\n🔔 [DESKTOP NOTIFICATION] {title}: {message}\n")

async def send_telegram_notification(message: str, reply_markup: Optional[dict] = None) -> bool:
    """Dispatches a message to the Telegram bot API using HTTP POST."""
    from config import settings
    if not settings.has_telegram:
        logger.debug("Telegram credentials not configured. Skipping Telegram notify.")
        return False
        
    import httpx
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info("Telegram notification sent successfully.")
                return True
            else:
                logger.error(f"Telegram returned status {response.status_code}: {response.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to connect to Telegram API: {e}")
        return False

async def notify_job_status(job_id: str, status: str, event: str, results: Optional[str] = None):
    """Formats and routes notifications depending on the background job lifecycle state."""
    emoji_map = {
        "running": "⚡",
        "completed": "✅",
        "failed": "❌",
        "paused": "🛡️",
        "cancelled": "⏹️"
    }
    emoji = emoji_map.get(status, "🔔")
    
    # 1. Dispatch Desktop Notification
    title = f"AERIS: Job {status.capitalize()}"
    desktop_message = f"Job {job_id} is now {status}. {event}"
    send_desktop_notification(title, desktop_message)
    
    # 2. Dispatch Telegram Notification
    telegram_msg = f"{emoji} **AERIS Job Alert**\n\n"
    telegram_msg += f"- **Job ID**: `{job_id}`\n"
    telegram_msg += f"- **Status**: `{status.upper()}`\n"
    telegram_msg += f"- **Event**: {event}\n"
    if results:
        telegram_msg += f"- **Result/Info**: {results[:600]}\n"
        
    reply_markup = None
    if status == "paused":
        # Attach interactive buttons for Remote Human-in-the-loop authorization
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve & Resume", "callback_data": f"approve_job_{job_id}"},
                    {"text": "❌ Cancel/Abort", "callback_data": f"cancel_job_{job_id}"}
                ]
            ]
        }
        
    await send_telegram_notification(telegram_msg, reply_markup=reply_markup)
