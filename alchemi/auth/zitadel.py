"""Zitadel token verification and management API helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
import jwt as pyjwt


@dataclass
class ZitadelSettings:
    enabled: bool
    issuer: Optional[str]
    audience: Optional[str]
    jwks_uri: Optional[str]
    account_id_claims: List[str]
    super_admin_roles: List[str]
    mgmt_api_base_url: Optional[str]
    mgmt_api_token: Optional[str]
    client_id: Optional[str]
    client_secret: Optional[str]
    callback_url: Optional[str]


def _split_csv(value: Optional[str], default: str) -> List[str]:
    raw = value if value is not None else default
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_zitadel_settings() -> ZitadelSettings:
    issuer = os.getenv("ZITADEL_ISSUER") or os.getenv("ZITADEL_ISSUER_URL")
    enabled_env = os.getenv("ZITADEL_ENABLED")
    if enabled_env is None:
        enabled = bool(issuer)
    else:
        enabled = enabled_env.strip().lower() in {"1", "true", "yes", "on"}
    jwks_uri = os.getenv("ZITADEL_JWKS_URI")
    if not jwks_uri and issuer:
        jwks_uri = f"{issuer.rstrip('/')}/.well-known/jwks.json"
    mgmt_base = os.getenv("ZITADEL_MGMT_API_BASE_URL")
    if not mgmt_base and issuer:
        mgmt_base = issuer.rstrip("/")

    return ZitadelSettings(
        enabled=enabled,
        issuer=issuer.rstrip("/") if issuer else None,
        audience=os.getenv("ZITADEL_AUDIENCE"),
        jwks_uri=jwks_uri,
        account_id_claims=_split_csv(
            os.getenv("ZITADEL_ACCOUNT_ID_CLAIMS"),
            "alchemi:account_id,account_id,urn:zitadel:iam:org:id,org_id",
        ),
        super_admin_roles=_split_csv(
            os.getenv("ZITADEL_SUPER_ADMIN_ROLES"),
            "super_admin",
        ),
        mgmt_api_base_url=mgmt_base,
        mgmt_api_token=os.getenv("ZITADEL_MGMT_API_TOKEN"),
        client_id=os.getenv("ZITADEL_CLIENT_ID"),
        client_secret=os.getenv("ZITADEL_CLIENT_SECRET"),
        callback_url=os.getenv("ZITADEL_CALLBACK_URL"),
    )


_jwk_clients: Dict[str, Any] = {}


def _jwk_client(jwks_uri: str):
    if jwks_uri not in _jwk_clients:
        _jwk_clients[jwks_uri] = pyjwt.PyJWKClient(jwks_uri)
    return _jwk_clients[jwks_uri]


def verify_zitadel_token(token: str, settings: Optional[ZitadelSettings] = None) -> Optional[Dict[str, Any]]:
    cfg = settings or get_zitadel_settings()
    if not cfg.enabled or not token or not cfg.jwks_uri:
        return None
    try:
        signing_key = _jwk_client(cfg.jwks_uri).get_signing_key_from_jwt(token)
        kwargs: Dict[str, Any] = {
            "key": signing_key.key,
            "algorithms": ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            "options": {"verify_exp": True},
        }
        if cfg.issuer:
            kwargs["issuer"] = cfg.issuer
        if cfg.audience:
            kwargs["audience"] = cfg.audience
        return pyjwt.decode(token, **kwargs)
    except Exception:
        return None


def decode_unverified(token: str) -> Optional[Dict[str, Any]]:
    try:
        return pyjwt.decode(token, options={"verify_signature": False, "verify_exp": False})
    except Exception:
        return None


def _extract_roles_from_claims(claims: Dict[str, Any]) -> List[str]:
    roles: List[str] = []
    direct = claims.get("roles") or claims.get("role")
    if isinstance(direct, str):
        roles.append(direct)
    elif isinstance(direct, list):
        roles.extend([str(r) for r in direct if r])

    for key, value in claims.items():
        if not key.endswith(":roles"):
            continue
        if isinstance(value, dict):
            roles.extend([str(k) for k in value.keys() if k])
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    roles.extend([str(k) for k in item.keys() if k])

    return list(dict.fromkeys([r for r in roles if r]))


def claims_to_context(
    claims: Dict[str, Any],
    settings: Optional[ZitadelSettings] = None,
) -> Dict[str, Any]:
    cfg = settings or get_zitadel_settings()
    roles = _extract_roles_from_claims(claims)
    scopes_value = claims.get("scopes") or claims.get("scope") or []
    if isinstance(scopes_value, str):
        scopes = [s for s in scopes_value.split(" ") if s]
    elif isinstance(scopes_value, list):
        scopes = [str(s) for s in scopes_value if s]
    else:
        scopes = []

    domains_value = (
        claims.get("product_domains_allowed")
        or claims.get("alchemi:product_domains_allowed")
        or claims.get("product_domains")
        or []
    )
    if isinstance(domains_value, str):
        domains = [domains_value]
    elif isinstance(domains_value, list):
        domains = [str(d) for d in domains_value if d]
    else:
        domains = []

    account_id = None
    for claim_name in cfg.account_id_claims:
        if claims.get(claim_name):
            account_id = str(claims.get(claim_name))
            break

    is_super = bool(claims.get("is_super_admin")) or any(r in set(cfg.super_admin_roles) for r in roles)

    return {
        "account_id": account_id,
        "roles": roles,
        "scopes": scopes,
        "domains": domains,
        "is_super_admin": is_super,
        "subject": claims.get("sub"),
    }


class ZitadelManagementClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout_seconds: float = 20.0,
    ):
        cfg = get_zitadel_settings()
        self.base_url = (base_url or cfg.mgmt_api_base_url or "").rstrip("/")
        self.token = token or cfg.mgmt_api_token
        self.client_id = cfg.client_id
        self.client_secret = cfg.client_secret
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.base_url and (self.token or (self.client_id and self.client_secret)))

    async def _resolve_token(self) -> str:
        if self.token:
            return self.token
        if not (self.base_url and self.client_id and self.client_secret):
            raise RuntimeError("ZITADEL management API token is not configured")
        token_url = f"{self.base_url}/oauth/v2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": os.getenv("ZITADEL_MGMT_SCOPE", "urn:zitadel:iam:org:project:id:zitadel:aud"),
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}
            raise RuntimeError(f"ZITADEL token request failed {resp.status_code}: {body}")
        data = resp.json()
        access_token = data.get("access_token")
        if not access_token:
            raise RuntimeError("ZITADEL token response missing access_token")
        self.token = str(access_token)
        return self.token

    async def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("ZITADEL management API is not configured")
        token = await self._resolve_token()
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.request(method.upper(), url, headers=headers, json=payload or {})
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text}
            raise RuntimeError(f"ZITADEL API error {resp.status_code}: {body}")
        try:
            return resp.json()
        except Exception:
            return {}

    async def add_user_grant(
        self,
        *,
        user_id: str,
        project_id: str,
        role_keys: List[str],
        organization_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {"projectId": project_id, "roleKeys": role_keys}
        if organization_id:
            payload["organizationId"] = organization_id
        return await self.request("POST", f"management/v1/users/{user_id}/grants", payload)

    async def add_project_role(
        self,
        *,
        project_id: str,
        key: str,
        display_name: str,
        group: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"key": key, "displayName": display_name}
        if group:
            payload["group"] = group
        return await self.request("POST", f"management/v1/projects/{project_id}/roles", payload)

    async def search_users_by_email(self, *, email: str) -> List[Dict[str, Any]]:
        email = (email or "").strip()
        if not email:
            return []

        query_payloads: List[Dict[str, Any]] = [
            {
                "queries": [
                    {
                        "emailQuery": {
                            "emailAddress": email,
                            "method": "TEXT_QUERY_METHOD_EQUALS",
                        }
                    }
                ],
                "limit": 5,
            },
            {
                "queries": [
                    {
                        "loginNameQuery": {
                            "loginName": email,
                            "method": "TEXT_QUERY_METHOD_EQUALS",
                        }
                    }
                ],
                "limit": 5,
            },
        ]

        for payload in query_payloads:
            try:
                response = await self.request("POST", "management/v1/users/_search", payload)
            except Exception:
                continue

            if not isinstance(response, dict):
                continue
            users = response.get("result") or response.get("users") or response.get("items") or []
            if isinstance(users, list) and users:
                return [u for u in users if isinstance(u, dict)]
        return []

    async def find_user_id_by_email(self, *, email: str) -> Optional[str]:
        users = await self.search_users_by_email(email=email)
        if not users:
            return None
        for user in users:
            user_id = user.get("id") or user.get("userId")
            if user_id:
                return str(user_id)
        return None
