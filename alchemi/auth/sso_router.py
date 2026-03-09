"""SSO routing backed by the Console control-plane identity bindings."""
from typing import Any, Dict

from alchemi.control_plane.service import resolve_sso_for_email as resolve_cp_sso


async def resolve_sso_for_email(
    email: str,
    prisma_client=None,
) -> Dict[str, Any]:
    if prisma_client is None:
        return {"method": "password", "account_id": None, "sso_enabled": False}

    try:
        return await resolve_cp_sso(prisma_client, email)
    except Exception:
        return {"method": "password", "account_id": None, "sso_enabled": False}
