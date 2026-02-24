"""
Account resolver - determines which account a user belongs to
based on email domain, API key, Zitadel claims, or admin credentials.
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


async def resolve_account_from_zitadel_claims(
    zitadel_sub: str,
    email: str,
    zitadel_org_id: Optional[str] = None,
    prisma_client=None,
) -> Optional[str]:
    """
    Resolve account_id from Zitadel OIDC claims.

    Resolution order:
    1. Match zitadel_org_id to Alchemi_AccountTable.metadata->>'auth_org_id'
    2. Fall back to email domain lookup (existing resolve_account_for_user)
    3. Fall back to Alchemi_AccountAdminTable lookup
    """
    if prisma_client is None:
        return None

    # 1. Try Zitadel org ID mapping
    if zitadel_org_id:
        try:
            # Query accounts where metadata contains matching auth_org_id
            accounts = await prisma_client.db.alchemi_accounttable.find_many(
                where={"status": "active"}
            )
            for account in accounts:
                metadata = account.metadata or {}
                if isinstance(metadata, str):
                    try:
                        import json
                        metadata = json.loads(metadata)
                    except (json.JSONDecodeError, TypeError):
                        metadata = {}
                if metadata.get("auth_org_id") == zitadel_org_id:
                    return account.account_id
        except Exception:
            pass

    # 2. Fall back to email domain lookup
    result = await resolve_account_for_user(email, prisma_client)
    if result:
        return result

    return None
