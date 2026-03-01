"""
Account resolver - determines which account a user belongs to
based on email domain, API key, Zitadel claims, or admin credentials.
"""
import os
from typing import List, Optional, Set, Tuple


def extract_email_domain(user_email: Optional[str]) -> Optional[str]:
    """Return normalized email domain or None."""
    if user_email is None:
        return None
    email = str(user_email).strip().lower()
    if "@" not in email:
        return None
    domain = email.split("@")[-1].strip().lower()
    return domain or None


async def resolve_account_for_user(
    user_email: Optional[str],
    prisma_client=None,
) -> Optional[str]:
    """
    Resolve the account_id for a user based on their email domain.
    Returns None for super admins.
    """
    domain = extract_email_domain(user_email)
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
    normalized_email = str(user_email or "").strip().lower()
    try:
        admin_record = await prisma_client.db.alchemi_accountadmintable.find_first(
            where={"user_email": normalized_email}
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


async def get_account_domain_and_admins(
    account_id: str,
    prisma_client=None,
) -> Tuple[Optional[str], Set[str]]:
    """Resolve account domain and admin emails for reconciliation."""
    if prisma_client is None or not account_id:
        return None, set()

    domain: Optional[str] = None
    admin_emails: Set[str] = set()

    try:
        account = await prisma_client.db.alchemi_accounttable.find_unique(
            where={"account_id": account_id}
        )
        if account and getattr(account, "domain", None):
            domain = str(account.domain).strip().lower() or None
    except Exception:
        domain = None

    try:
        admins = await prisma_client.db.alchemi_accountadmintable.find_many(
            where={"account_id": account_id}
        )
        for admin in admins:
            email = str(getattr(admin, "user_email", "") or "").strip().lower()
            if email:
                admin_emails.add(email)
    except Exception:
        pass

    return domain, admin_emails


async def reconcile_identity_account_links(
    account_id: str,
    prisma_client=None,
    max_scan: int = 5000,
    reassign_mismatched: bool = False,
) -> List[str]:
    """
    Backfill LiteLLM_UserTable.account_id for users that belong to account_id.

    Match criteria:
    - user_email domain equals account domain, OR
    - user_email exists in account admin table
    By default, only unassigned users (NULL or empty account_id) are updated.
    If `reassign_mismatched=True`, users matched by domain/admin-email are reassigned
    to the target account when currently linked to a different account_id.
    """
    if prisma_client is None or not account_id:
        return []

    domain, admin_emails = await get_account_domain_and_admins(
        account_id=account_id,
        prisma_client=prisma_client,
    )
    if not domain and not admin_emails:
        return []

    try:
        if reassign_mismatched:
            candidates = await prisma_client.db.litellm_usertable.find_many(
                take=max_scan,
            )
        else:
            candidates = await prisma_client.db.litellm_usertable.find_many(
                where={"OR": [{"account_id": None}, {"account_id": ""}]},
                take=max_scan,
            )
    except Exception:
        return []

    updated_ids: List[str] = []
    for user in candidates:
        email = str(getattr(user, "user_email", "") or "").strip().lower()
        if not email or "@" not in email:
            continue
        email_domain = email.split("@")[-1]
        should_link = (domain is not None and email_domain == domain) or (email in admin_emails)
        if not should_link:
            continue

        user_id = str(getattr(user, "user_id", "") or "").strip()
        if not user_id:
            continue

        current_account_id = str(getattr(user, "account_id", "") or "").strip()
        if current_account_id == account_id:
            continue
        if current_account_id and not reassign_mismatched:
            continue

        try:
            await prisma_client.db.litellm_usertable.update(
                where={"user_id": user_id},
                data={"account_id": account_id},
            )
            updated_ids.append(user_id)
        except Exception:
            continue

    return updated_ids
