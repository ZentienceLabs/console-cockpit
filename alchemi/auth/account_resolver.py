"""Account resolver for the Console control plane."""
import os
from typing import Optional

from alchemi.control_plane.service import resolve_account_for_user as resolve_cp_account


async def resolve_account_for_user(
    user_email: Optional[str],
    prisma_client=None,
    zitadel_sub: Optional[str] = None,
) -> Optional[str]:
    """
    Resolve the active account for a user.

    Preference order:
    1. Control-plane user + membership graph
    2. Legacy account-admin table fallback
    3. Legacy email-domain fallback
    """
    if prisma_client is None:
        return None

    resolved = await resolve_cp_account(
        prisma_client,
        user_email=user_email,
        zitadel_sub=zitadel_sub,
    )
    if resolved:
        return resolved

    if user_email is None:
        return None

    try:
        admin_record = await prisma_client.db.alchemi_accountadmintable.find_first(
            where={"user_email": user_email}
        )
        if admin_record:
            return admin_record.account_id
    except Exception:
        pass

    domain = user_email.split("@")[-1] if "@" in user_email else None
    if domain is None:
        return None

    try:
        account = await prisma_client.db.alchemi_accounttable.find_first(
            where={"domain": domain, "status": "active"}
        )
        if account:
            return account.account_id
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
