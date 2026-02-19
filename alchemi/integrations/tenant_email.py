"""
Per-tenant SMTP email sending.

When ``EMAIL_MODE=tenant_first`` is set, the system will check for SMTP
configuration stored in ``Alchemi_AccountTable.metadata.smtp_config``
before falling back to the central email queue.

SMTP config structure stored in account metadata::

    {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "user@example.com",
        "smtp_password": "secret",
        "sender_email": "noreply@example.com",
        "sender_name": "Alchemi Studio"
    }
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from litellm._logging import verbose_proxy_logger


def get_email_mode() -> str:
    """Return the configured email mode: 'central' or 'tenant_first'."""
    return os.getenv("EMAIL_MODE", "central").lower()


async def get_tenant_smtp_config(account_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Retrieve SMTP configuration for a given account from its metadata.

    Returns None if the account has no SMTP config or if account_id is None.
    """
    if not account_id:
        return None

    try:
        from litellm.proxy.proxy_server import prisma_client

        if prisma_client is None:
            return None

        account = await prisma_client.db.alchemi_accounttable.find_unique(
            where={"account_id": account_id}
        )
        if not account or not account.metadata:
            return None

        meta = account.metadata if isinstance(account.metadata, dict) else {}
        smtp_config = meta.get("smtp_config")
        if smtp_config and isinstance(smtp_config, dict) and smtp_config.get("smtp_host"):
            return smtp_config
    except Exception as e:
        verbose_proxy_logger.warning(f"Error reading tenant SMTP config: {e}")

    return None


def send_email_via_smtp(
    smtp_config: Dict[str, Any],
    to_email: str,
    subject: str,
    html_body: str,
) -> bool:
    """
    Send an email using the provided SMTP config dict.

    Returns True on success, False on failure.
    """
    try:
        host = smtp_config["smtp_host"]
        port = int(smtp_config.get("smtp_port", 587))
        username = smtp_config.get("smtp_username", "")
        password = smtp_config.get("smtp_password", "")
        sender_email = smtp_config.get("sender_email", username)
        sender_name = smtp_config.get("sender_name", "Alchemi Studio")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            if username and password:
                server.login(username, password)
            server.sendmail(sender_email, to_email, msg.as_string())

        verbose_proxy_logger.info(f"Tenant SMTP email sent to {to_email} via {host}")
        return True
    except Exception as e:
        verbose_proxy_logger.warning(f"Tenant SMTP send failed: {e}")
        return False


async def send_tenant_invitation_email(
    account_id: Optional[str],
    user_email: str,
    user_name: str,
    inviter_name: str,
    invite_link: str,
    workspace_name: str = "Alchemi Studio Console",
) -> bool:
    """
    Try sending an invitation email using the tenant's own SMTP config.

    Returns True if sent successfully, False if no tenant config or send failed.
    """
    smtp_config = await get_tenant_smtp_config(account_id)
    if not smtp_config:
        return False

    subject = f"You've been invited to {workspace_name}"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2>Welcome to {workspace_name}!</h2>
        <p>Hi {user_name},</p>
        <p><strong>{inviter_name}</strong> has invited you to join <strong>{workspace_name}</strong>.</p>
        <p style="margin: 24px 0;">
            <a href="{invite_link}"
               style="background-color: #6366f1; color: white; padding: 12px 24px;
                      text-decoration: none; border-radius: 6px; font-weight: bold;">
                Accept Invitation
            </a>
        </p>
        <p style="color: #666; font-size: 12px;">
            Or copy this link: {invite_link}
        </p>
    </div>
    """

    return send_email_via_smtp(smtp_config, user_email, subject, html_body)
