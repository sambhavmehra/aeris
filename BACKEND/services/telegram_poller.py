import asyncio
import logging
import json
import httpx
from services.job_manager import get_job_manager
from tools.tool_permissions import get_permission_system
from config import settings

logger = logging.getLogger("aeris.telegram_poller")

async def poll_telegram_updates():
    """Loops long-polling updates from Telegram and handles callbacks for remote approval."""
    if not settings.has_telegram:
        logger.info("Telegram not configured. Poller will not run.")
        return

    bot_token = settings.TELEGRAM_BOT_TOKEN
    offset = 0
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"

    logger.info("AERIS Telegram Poller service started.")
    
    async with httpx.AsyncClient(timeout=35.0) as client:
        while True:
            try:
                params = {
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": ["callback_query", "message"]
                }
                response = await client.get(url, params=params)
                if response.status_code != 200:
                    logger.warning(f"Telegram polling failed with status: {response.status_code}")
                    await asyncio.sleep(10)
                    continue
                    
                data = response.json()
                if not data.get("ok"):
                    logger.warning(f"Telegram update error: {data.get('description')}")
                    await asyncio.sleep(10)
                    continue

                for update in data.get("result", []):
                    update_id = update["update_id"]
                    offset = update_id + 1
                    
                    # Handle Callback Queries (Buttons)
                    if "callback_query" in update:
                        await handle_callback_query(client, bot_token, update["callback_query"])
                    # Handle Incoming Text Messages (Commands)
                    elif "message" in update:
                        await handle_text_message(client, bot_token, update["message"])
                        
            except asyncio.CancelledError:
                logger.info("Telegram Poller task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in Telegram Poller loop: {e}")
                await asyncio.sleep(10)

async def handle_callback_query(client: httpx.AsyncClient, bot_token: str, query: dict):
    """Processes inline button clicks to approve or cancel background tasks."""
    query_id = query["id"]
    data = query.get("data", "")
    message = query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    msg_id = message.get("message_id")
    
    # 1. Answer callback query to stop the Telegram loading wheel
    answer_url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    try:
        await client.post(answer_url, json={"callback_query_id": query_id})
    except Exception as e:
        logger.warning(f"Failed to answer callback query: {e}")

    if data.startswith("repair_code_"):
        repair_id = data.replace("repair_code_", "")
        from services.workspace_watcher import get_workspace_watcher
        watcher = get_workspace_watcher()
        result = await watcher.trigger_repair(repair_id)
        await edit_telegram_message(
            client, bot_token, chat_id, msg_id,
            f"🔧 **Auto-Repair Executed**\n- Repair ID: `{repair_id}`\n\n{result}"
        )
        return
    elif data.startswith("ignore_code_"):
        repair_id = data.replace("ignore_code_", "")
        from services.workspace_watcher import get_workspace_watcher
        watcher = get_workspace_watcher()
        watcher.clear_repair(repair_id)
        await edit_telegram_message(
            client, bot_token, chat_id, msg_id,
            f"❌ **Alert Dismissed**\n- Diagnostics for repair ID `{repair_id}` ignored."
        )
        return

    job_id = None
    action = None
    if data.startswith("approve_job_"):
        job_id = data.replace("approve_job_", "")
        action = "approve"
    elif data.startswith("cancel_job_"):
        job_id = data.replace("cancel_job_", "")
        action = "cancel"
        
    if not job_id or not action:
        return

    job_manager = get_job_manager()
    job = job_manager.get_job(job_id)
    
    if not job:
        await edit_telegram_message(client, bot_token, chat_id, msg_id, f"❌ Sir, background job `{job_id}` not found in system records.")
        return

    # Load approval file
    from config import settings
    pending_file = settings.DATA_DIR / "pending_approval.json"
    state = None
    if pending_file.exists():
        try:
            with open(pending_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read pending approval file: {e}")

    if action == "approve":
        # Check if the pending task matches the job_id
        if state and state.get("task_id") == job_id:
            tool_name = state.get("tool_name_pending")
            # Approve tool execution in permissions system
            get_permission_system().approve_for_session(tool_name)
            
            # Remove pending approval state file
            try:
                pending_file.unlink()
            except Exception:
                pass
                
            # Resume background job asynchronously based on the saving core
            agent_core = state.get("agent", "Brain")
            
            if agent_core == "HackerBrain":
                from hacker_brain import hacker_brain
                asyncio.create_task(hacker_brain._run_background_job_resume(job_id, state))
            else:
                from brain import brain
                asyncio.create_task(brain._run_background_job_resume(job_id, state))
                
            await edit_telegram_message(
                client, bot_token, chat_id, msg_id, 
                f"✅ **Approved & Resumed**\n- Job `{job_id}` has been authorized to run `{tool_name}`.\n- Execution resuming in background..."
            )
        else:
            await edit_telegram_message(
                client, bot_token, chat_id, msg_id, 
                f"⚠️ Sir, job `{job_id}` doesn't have a pending approval state currently. (It may have been handled already.)"
            )
            
    elif action == "cancel":
        success = job_manager.cancel_job(job_id)
        # Clear approval state if it matches
        if state and state.get("task_id") == job_id:
            try:
                pending_file.unlink()
            except Exception:
                pass
                
        await edit_telegram_message(
            client, bot_token, chat_id, msg_id, 
            f"⏹️ **Job Aborted**\n- Background job `{job_id}` has been cancelled by remote command."
        )

async def edit_telegram_message(client: httpx.AsyncClient, bot_token: str, chat_id: int, message_id: int, new_text: str):
    """Edits the text of an existing Telegram message to clean up markup inline buttons on response."""
    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": new_text,
        "parse_mode": "Markdown",
        "reply_markup": None
    }
    try:
        await client.post(url, json=payload)
    except Exception as e:
        logger.error(f"Failed to edit Telegram message: {e}")


async def handle_text_message(client: httpx.AsyncClient, bot_token: str, message: dict):
    """Processes incoming text commands/messages from authorized Telegram users and executes them via the Brain."""
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()
    
    if not text:
        return

    # Verify authorization (only process commands from whitelisted chat ID)
    if str(chat_id) != str(settings.TELEGRAM_CHAT_ID):
        logger.warning(f"BLOCKING unauthorized message from chat ID {chat_id}: {text}")
        return

    logger.info(f"Received authorized Telegram command: {text}")

    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Send typing status indicator
    try:
        action_url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"
        await client.post(action_url, json={"chat_id": chat_id, "action": "typing"}, timeout=2.0)
    except Exception:
        pass

    try:
        from brain import brain
        # Process command via Aeris Brain
        result = await brain.process(text)
        
        # Get response text
        response_text = result.get("response") or result.get("output") or "Sir, execution completed."
        
        # Split message if it exceeds Telegram's 4096 character limit
        if len(response_text) > 4000:
            chunks = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
            for chunk in chunks:
                payload = {
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "Markdown"
                }
                res = await client.post(send_url, json=payload)
                if res.status_code != 200:
                    payload.pop("parse_mode", None)
                    await client.post(send_url, json=payload)
        else:
            payload = {
                "chat_id": chat_id,
                "text": response_text,
                "parse_mode": "Markdown"
            }
            res = await client.post(send_url, json=payload)
            if res.status_code != 200:
                payload.pop("parse_mode", None)
                await client.post(send_url, json=payload)
                
    except Exception as e:
        logger.exception("Error processing Telegram text command")
        err_msg = f"❌ **Sir, an error occurred while executing command:**\n`{str(e)}`"
        await client.post(send_url, json={
            "chat_id": chat_id,
            "text": err_msg,
            "parse_mode": "Markdown"
        })
