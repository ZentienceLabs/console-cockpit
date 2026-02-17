"""
Account resolver - determines which account a user belongs to
based on email domain, API key, or admin credentials.
"""
import os
from typing import Optional


async def resolve_account_for_user(
    user_email: Optional[str],
    prisma_client=None,
) -> Optional[str]:
    """
    Resolve the account_id for a user based on their email domain.
    Returns None for super admins.
    """
    if user_email is None:
        return None

    domain = user_email.split("@")[-1] if "@" in user_email else None
    if domain is None:
        return None

    if prisma_client is None:
        return None

    try:
        account = await prisma_client.db.alchemi_accounttable.find_first(
            where={"domain": domain, "status": "active"}
        )
        if account:
            return account.account_id
    except Exception:
        pass

    # Check if user is an account admin
    try:
        admin_record = await prisma_client.db.alchemi_accountadmintable.find_first(
            where={"user_email": user_email}
        )
        if admin_record:
            return admin_record.account_id
    except Exception:
        pass

    return None


async def resolve_account_from_key(
    token_record,
) -> Optional[str]:
    """Resolve account_id from an API key's token record."""
    if token_record is None:
        return None
    return getattr(token_record, "account_id", None)


def is_default_admin(username: Optional[str]) -> bool:
    """Check if the given username matches the super admin credentials."""
    ui_username = os.getenv("UI_USERNAME")
    return username is not None and ui_username is not None and username == ui_username
