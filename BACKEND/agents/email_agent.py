"""
AERIS Email Agent — Sends emails to recipients via SMTP configuration.
Uses Brevo (Sendinblue) or any other configured SMTP relay.
"""

import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from config import settings

logger = logging.getLogger("aeris.agent.email")


class EmailAgent(BaseAgent):
    """Sends emails using settings-configured SMTP relay."""

    def __init__(self):
        super().__init__(
            name="EmailAgent",
            description="Sends emails to recipients via SMTP configurations",
            task_domain="email",
            version="1.0.0",
            capabilities=[
                "Send Email",
                "Compose Email Content",
                "SMTP Authentication",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """Parse email recipient, subject, and body from message using LLM classification."""
        prompt = (
            "You are the planner for the EmailAgent. Extract the email details "
            "(recipient email or name, subject, body/content) from the user's message.\n"
            "If the subject is not specified, generate a short, descriptive subject line based on the email body.\n"
            "If the email body/content is not specified, construct a polite and appropriate message based on the user's instructions.\n"
            "Respond with ONLY JSON:\n"
            '{"recipient": "recipient_email_or_name", "subject": "subject_line", "body": "email_body_content"}\n\n'
            f"User message: {message}"
        )
        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            details = json.loads(raw)
            return details
        except Exception as e:
            logger.error(f"Failed to parse email details in think(): {e}")
            return {"recipient": "", "subject": "AERIS Notification", "body": message}

    async def execute(self, plan: Any) -> Any:
        """Execute email sending via SMTP server."""
        recipient = plan.get("recipient", "").strip()
        subject = plan.get("subject", "AERIS Notification").strip()
        body = plan.get("body", "").strip()

        if not recipient:
            return {"success": False, "error": "No recipient specified."}

        # Resolve recipient name if it is not an email
        if "@" not in recipient:
            name_lower = recipient.lower()
            if name_lower in ("me", "myself", "sambhav", "sambhav mehra"):
                recipient_email = "sambhavmehra07@gmail.com"
            else:
                recipient_email = f"{recipient.lower().replace(' ', '')}@example.com"
                logger.info(f"Unresolved name '{recipient}', defaulting to {recipient_email}")
        else:
            recipient_email = recipient

        # Retrieve SMTP configuration from settings
        smtp_server = settings.SMTP_SERVER
        smtp_port = settings.SMTP_PORT
        smtp_login = settings.SMTP_LOGIN
        smtp_password = settings.SMTP_PASSWORD
        sender_email = settings.BREVO_SENDER_EMAIL
        if not sender_email:
            if smtp_login and "@" in smtp_login and "smtp-brevo.com" not in smtp_login:
                sender_email = smtp_login
            else:
                sender_email = "noreply@aeris.io"
        
        sender_name = settings.BREVO_SENDER_NAME or settings.ASSISTANT_NAME

        if not smtp_login or not smtp_password:
            return {
                "success": False,
                "error": "SMTP login or password is not configured in Settings/.env.",
            }

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = recipient_email

            if "<html>" in body.lower() or "<p>" in body.lower() or "<br>" in body.lower() or "</div>" in body.lower():
                msg.attach(MIMEText(body, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))

            logger.info(f"Connecting to SMTP server {smtp_server}:{smtp_port}...")
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            
            logger.info(f"Logging in as {smtp_login}...")
            server.login(smtp_login, smtp_password)
            
            logger.info(f"Sending email to {recipient_email}...")
            server.send_message(msg)
            server.quit()
            logger.info("Email sent successfully.")

            return {
                "success": True,
                "recipient": recipient_email,
                "subject": subject,
                "message": f"Email successfully sent to {recipient_email}.",
            }
        except Exception as e:
            logger.error(f"SMTP error while sending email: {e}")
            return {"success": False, "error": str(e)}

    async def report(self, results: Any) -> str:
        """Format a human-readable response summarizing the outcome."""
        if results.get("success"):
            return (
                f"✅ **Email sent successfully!**\n\n"
                f"- **To:** `{results.get('recipient')}`\n"
                f"- **Subject:** {results.get('subject')}\n\n"
                f"Your message was successfully relayed through the Brevo SMTP server."
            )
        else:
            return (
                f"❌ **Failed to send email.**\n\n"
                f"**Error Details:** {results.get('error')}\n\n"
                f"Please verify your SMTP configurations and credentials in the `.env` file."
            )
