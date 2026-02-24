"""
Zitadel webhook handler for user provisioning.
Receives events from Zitadel (e.g., user.human.added) and auto-provisions
users in the LiteLLM_UserTable with the correct account_id.
"""
import os
import hmac
import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["Zitadel Webhook"])
logger = logging.getLogger(__name__)

_SIGNATURE_HEADERS = (
    "x-zitadel-signature",
    "x-zitadel-signature-sha256",
    "x-webhook-signature",
)


def _verify_webhook_signature(raw_body: bytes, request: Request) -> None:
    """
    Verify Zitadel webhook signature (HMAC-SHA256) if secret is configured.

    The secret is optional for backwards compatibility. If
    ZITADEL_WEBHOOK_SECRET is set, signature verification is enforced.
    """
    webhook_secret = os.getenv("ZITADEL_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        return

    signature: Optional[str] = None
    for header in _SIGNATURE_HEADERS:
        value = request.headers.get(header)
        if value:
            signature = value.strip()
            break

    if not signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature.")

    # Support "sha256=<hex>" or plain hex
    if "=" in signature:
        _, signature = signature.split("=", 1)
    signature = signature.strip().lower()

    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected.lower()):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")


@router.post("/zitadel/webhook")
async def handle_zitadel_webhook(request: Request):
    """
    Handle Zitadel webhook events.
    Currently supports: user.human.added
    Auto-provisions users in LiteLLM_UserTable with resolved account_id.
    """
    raw_body = await request.body()
    _verify_webhook_signature(raw_body, request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    # Zitadel may send a single event or a batch
    events = body if isinstance(body, list) else [body]

    provisioned = 0
    for event_data in events:
        event_type = event_data.get("event_type", "")

        if event_type != "user.human.added":
            continue

        zitadel_user_id = event_data.get("aggregateID")
        zitadel_org_id = event_data.get("resourceOwner")
        payload = event_data.get("event_payload", {})

        if not zitadel_user_id or not payload:
            continue

        email = str(payload.get("email", "")).strip().lower()
        display_name = payload.get("displayName", "")
        first_name = payload.get("firstName", "")
        last_name = payload.get("lastName", "")
        name = display_name or f"{first_name} {last_name}".strip()

        if not email:
            continue

        try:
            from litellm.proxy.proxy_server import prisma_client

            if prisma_client is None:
                continue

            # Resolve account from Zitadel org
            from alchemi.auth.account_resolver import resolve_account_from_zitadel_claims

            account_id = await resolve_account_from_zitadel_claims(
                zitadel_sub=zitadel_user_id,
                email=email,
                zitadel_org_id=zitadel_org_id,
                prisma_client=prisma_client,
            )

            # Check if user already exists (by email or sso_user_id)
            existing = await prisma_client.db.litellm_usertable.find_first(
                where={
                    "OR": [
                        {"user_email": email},
                        {"sso_user_id": zitadel_user_id},
                    ]
                }
            )
            if existing:
                update_data = {}
                if not existing.sso_user_id:
                    update_data["sso_user_id"] = zitadel_user_id
                if not existing.account_id and account_id:
                    update_data["account_id"] = account_id
                if update_data:
                    await prisma_client.db.litellm_usertable.update(
                        where={"user_id": existing.user_id},
                        data=update_data,
                    )
                continue

            # Determine role
            from alchemi.auth.super_admin import is_super_admin_zitadel

            user_role = "proxy_admin" if is_super_admin_zitadel(email) else "internal_user"

            await prisma_client.db.litellm_usertable.create(
                data={
                    # Keep user_id aligned with OIDC callback identity.
                    "user_id": email,
                    "user_email": email,
                    "user_alias": name or None,
                    "user_role": user_role,
                    "sso_user_id": zitadel_user_id,
                    "account_id": account_id,
                    "spend": 0.0,
                    "models": [],
                    "teams": [],
                }
            )
            provisioned += 1

        except Exception as e:
            # Log error but don't fail the webhook
            logger.warning("Failed to process Zitadel webhook event: %s", e)
            continue

    return {"status": "ok", "provisioned": provisioned}
