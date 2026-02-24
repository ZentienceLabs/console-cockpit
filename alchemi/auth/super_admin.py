"""Super admin authentication and authorization logic."""
import os
from typing import Optional


def verify_super_admin(username: str, password: str) -> bool:
    """Verify super admin credentials against environment variables."""
    expected_username = os.getenv("UI_USERNAME")
    expected_password = os.getenv("UI_PASSWORD")
    if not expected_username or not expected_password:
        return False
    return username == expected_username and password == expected_password


def is_super_admin_user(user_id: Optional[str], user_role: Optional[str] = None) -> bool:
    """Check if a user_id corresponds to the super admin."""
    ui_username = os.getenv("UI_USERNAME")
    return user_id is not None and user_id == ui_username


def is_super_admin_zitadel(email: str) -> bool:
    """Check if email is in the SUPER_ADMIN_EMAILS environment variable."""
    super_admin_emails = os.getenv("SUPER_ADMIN_EMAILS", "")
    if not super_admin_emails:
        return False
    return email.lower() in [e.strip().lower() for e in super_admin_emails.split(",")]
