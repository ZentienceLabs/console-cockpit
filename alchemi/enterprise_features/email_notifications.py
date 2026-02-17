"""Email notifications system for key management events."""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
import traceback

from litellm.integrations.custom_logger import CustomLogger


class BaseEmailLogger(CustomLogger):
    """Base email logger that all email loggers extend."""

    def __init__(self, internal_usage_cache=None, **kwargs):
        super().__init__()
        self.internal_usage_cache = internal_usage_cache
        self.from_email = os.getenv("SMTP_SENDER_EMAIL", os.getenv("SMTP_USERNAME", ""))


class SMTPEmailLogger(BaseEmailLogger):
    """Email logger using SMTP."""

    def __init__(self, internal_usage_cache=None, **kwargs):
        super().__init__(internal_usage_cache=internal_usage_cache, **kwargs)
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")

    async def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())
            return True
        except Exception:
            traceback.print_exc()
            return False


class SendGridEmailLogger(BaseEmailLogger):
    """Email logger using SendGrid API."""

    def __init__(self, internal_usage_cache=None, **kwargs):
        super().__init__(internal_usage_cache=internal_usage_cache, **kwargs)
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "")

    async def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "personalizations": [{"to": [{"email": to_email}]}],
                        "from": {"email": self.from_email},
                        "subject": subject,
                        "content": [{"type": "text/html", "value": html_body}],
                    },
                )
                return response.status_code in (200, 202)
        except Exception:
            traceback.print_exc()
            return False


class ResendEmailLogger(BaseEmailLogger):
    """Email logger using Resend API."""

    def __init__(self, internal_usage_cache=None, **kwargs):
        super().__init__(internal_usage_cache=internal_usage_cache, **kwargs)
        self.resend_api_key = os.getenv("RESEND_API_KEY", "")

    async def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {self.resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": self.from_email,
                        "to": to_email,
                        "subject": subject,
                        "html": html_body,
                    },
                )
                return response.status_code == 200
        except Exception:
            traceback.print_exc()
            return False


class AlchemiEmailNotifier:
    """Unified email notification sender - convenience wrapper."""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "")
        self.resend_api_key = os.getenv("RESEND_API_KEY", "")

    def _get_logger(self):
        if self.sendgrid_api_key:
            return SendGridEmailLogger()
        elif self.resend_api_key:
            return ResendEmailLogger()
        elif self.smtp_host:
            return SMTPEmailLogger()
        return None

    def is_configured(self) -> bool:
        return self._get_logger() is not None

    async def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        logger = self._get_logger()
        if logger:
            return await logger.send_email(to_email, subject, html_body)
        return False

    async def send_key_created_email(self, user_email: str, key_info: Dict[str, Any]) -> bool:
        subject = "Alchemi Studio Console - New API Key Created"
        html_body = f"""
        <h2>New API Key Created</h2>
        <p>A new API key has been created for your account.</p>
        <ul>
            <li><strong>Key Name:</strong> {key_info.get('key_name', 'N/A')}</li>
            <li><strong>Created:</strong> {key_info.get('created_at', 'N/A')}</li>
        </ul>
        <p>If you did not create this key, please contact your administrator.</p>
        <p>- Alchemi Studio Console</p>
        """
        return await self.send_email(user_email, subject, html_body)

    async def send_key_rotated_email(self, user_email: str, key_info: Dict[str, Any]) -> bool:
        subject = "Alchemi Studio Console - API Key Rotated"
        html_body = f"""
        <h2>API Key Rotated</h2>
        <p>Your API key has been rotated.</p>
        <ul>
            <li><strong>Key Name:</strong> {key_info.get('key_name', 'N/A')}</li>
            <li><strong>Rotated:</strong> {key_info.get('rotated_at', 'N/A')}</li>
        </ul>
        <p>Please update your applications with the new key.</p>
        <p>- Alchemi Studio Console</p>
        """
        return await self.send_email(user_email, subject, html_body)

    async def send_invitation_email(
        self, user_email: str, invite_link: str, account_name: str = "Alchemi Studio Console"
    ) -> bool:
        subject = f"You've been invited to {account_name}"
        html_body = f"""
        <h2>You're Invited!</h2>
        <p>You've been invited to join <strong>{account_name}</strong> on Alchemi Studio Console.</p>
        <p><a href="{invite_link}">Click here to accept the invitation</a></p>
        <p>- Alchemi Studio Console</p>
        """
        return await self.send_email(user_email, subject, html_body)
