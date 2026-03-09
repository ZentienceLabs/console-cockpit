import os
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx


DEFAULT_ZITADEL_AUDIENCE = "openid profile email urn:zitadel:iam:org:project:id:zitadel:aud"


class ZitadelConfigurationError(RuntimeError):
    """Raised when the backend is missing Zitadel management credentials."""


class ZitadelAPIError(RuntimeError):
    """Raised when a Zitadel API request fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        detail: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class ZitadelClient:
    def __init__(
        self,
        *,
        issuer: str,
        pat: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        audience: str = DEFAULT_ZITADEL_AUDIENCE,
        timeout: float = 20.0,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.pat = pat
        self.client_id = client_id
        self.client_secret = client_secret
        self.audience = audience
        self.timeout = timeout
        self._access_token: Optional[str] = None
        self._access_token_expires_at: float = 0.0

    @classmethod
    def from_env(cls) -> "ZitadelClient":
        issuer = (
            os.getenv("ALCHEMI_ZITADEL_API_URL")
            or os.getenv("ALCHEMI_ZITADEL_ISSUER")
            or os.getenv("ZITADEL_ISSUER")
            or os.getenv("ZITADEL_ISSUER_URL")
        )
        if not issuer:
            raise ZitadelConfigurationError(
                "Set ALCHEMI_ZITADEL_API_URL or ALCHEMI_ZITADEL_ISSUER for Console-managed identity."
            )

        pat = os.getenv("ALCHEMI_ZITADEL_PAT") or os.getenv(
            "ALCHEMI_ZITADEL_SERVICE_PAT"
        )
        client_id = os.getenv("ALCHEMI_ZITADEL_SERVICE_CLIENT_ID")
        client_secret = os.getenv("ALCHEMI_ZITADEL_SERVICE_CLIENT_SECRET")

        if not pat and not (client_id and client_secret):
            raise ZitadelConfigurationError(
                "Configure ALCHEMI_ZITADEL_PAT or ALCHEMI_ZITADEL_SERVICE_CLIENT_ID / "
                "ALCHEMI_ZITADEL_SERVICE_CLIENT_SECRET for Console-managed identity."
            )

        audience = os.getenv("ALCHEMI_ZITADEL_AUDIENCE", DEFAULT_ZITADEL_AUDIENCE)
        return cls(
            issuer=issuer,
            pat=pat,
            client_id=client_id,
            client_secret=client_secret,
            audience=audience,
        )

    @property
    def configured(self) -> bool:
        return bool(self.pat or (self.client_id and self.client_secret))

    async def _get_access_token(self) -> str:
        if self.pat:
            return self.pat

        if self._access_token and time.time() < self._access_token_expires_at - 30:
            return self._access_token

        if not self.client_id or not self.client_secret:
            raise ZitadelConfigurationError(
                "Zitadel client credentials are not configured."
            )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.issuer}/oauth/v2/token",
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "client_credentials",
                    "scope": self.audience,
                },
            )

        if response.status_code >= 400:
            detail: Any
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise ZitadelAPIError(
                "Failed to obtain a Zitadel management access token.",
                status_code=response.status_code,
                detail=detail,
            )

        data = response.json()
        self._access_token = data["access_token"]
        self._access_token_expires_at = time.time() + int(data.get("expires_in") or 60)
        return self._access_token

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if org_id:
            headers["x-zitadel-orgid"] = org_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method,
                f"{self.issuer}{path}",
                headers=headers,
                json=json_body,
            )

        if response.status_code >= 400:
            detail: Any
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise ZitadelAPIError(
                f"Zitadel API request failed for {method} {path}",
                status_code=response.status_code,
                detail=detail,
            )

        if not response.content:
            return {}
        try:
            payload = response.json()
            return payload if isinstance(payload, dict) else {"result": payload}
        except Exception:
            return {"raw": response.text}

    async def create_organization(self, *, name: str) -> Dict[str, Any]:
        data = await self.request(
            "POST",
            "/v2/organizations",
            json_body={"name": name},
        )
        return {
            "organization_id": data.get("organizationId") or data.get("id"),
            "raw": data,
        }

    async def search_organizations_by_name(self, *, name: str) -> list[Dict[str, Any]]:
        data = await self.request(
            "POST",
            "/admin/v1/orgs/_search",
            json_body={
                "queries": [
                    {
                        "nameQuery": {
                            "name": name,
                            "method": "TEXT_QUERY_METHOD_EQUALS",
                        }
                    }
                ]
            },
        )
        results = data.get("result") or []
        normalized: list[Dict[str, Any]] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "organization_id": row.get("id"),
                    "name": row.get("name"),
                    "primary_domain": row.get("primaryDomain"),
                    "state": row.get("state"),
                    "raw": row,
                }
            )
        return normalized

    async def list_organizations(self, *, limit: int = 200) -> list[Dict[str, Any]]:
        data = await self.request(
            "POST",
            "/admin/v1/orgs/_search",
            json_body={"limit": max(1, min(limit, 500))},
        )
        results = data.get("result") or []
        normalized: list[Dict[str, Any]] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "organization_id": row.get("id"),
                    "name": row.get("name"),
                    "primary_domain": row.get("primaryDomain"),
                    "state": row.get("state"),
                    "raw": row,
                }
            )
        return normalized

    async def get_organization(self, *, org_id: str) -> Dict[str, Any]:
        data = await self.request("GET", f"/admin/v1/orgs/{quote(org_id, safe='')}")
        row = data.get("org") if isinstance(data.get("org"), dict) else data
        return {
            "organization_id": row.get("id"),
            "name": row.get("name"),
            "primary_domain": row.get("primaryDomain"),
            "state": row.get("state"),
            "raw": data,
        }

    async def create_human_user(
        self,
        *,
        org_id: str,
        email: str,
        given_name: str,
        family_name: str,
        display_name: str,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "organization": {"orgId": org_id},
            "username": email,
            "profile": {
                "givenName": given_name,
                "familyName": family_name,
                "displayName": display_name,
                "preferredLanguage": "en",
            },
            "email": {
                "email": email,
                "isVerified": True,
            },
        }
        if password:
            body["password"] = {
                "password": password,
                "changeRequired": True,
            }
        data = await self.request(
            "POST",
            "/v2/users/human",
            json_body=body,
        )
        return {
            "user_id": data.get("userId") or data.get("id"),
            "raw": data,
        }

    async def create_invite_code(self, *, user_id: str) -> Dict[str, Any]:
        data = await self.request(
            "POST",
            f"/v2/users/{user_id}/invite_code",
            json_body={},
        )
        return {
            "invite_code": data.get("inviteCode"),
            "raw": data,
        }

    async def create_machine_user(
        self,
        *,
        org_id: str,
        username: str,
        name: str,
    ) -> Dict[str, Any]:
        data = await self.request(
            "POST",
            "/v2/users/new",
            json_body={
                "organizationId": org_id,
                "username": username,
                "machine": {
                    "name": name,
                },
            },
        )
        return {
            "user_id": data.get("userId") or data.get("id"),
            "raw": data,
        }

    async def add_personal_access_token(
        self,
        *,
        user_id: str,
        token_name: str = "console-scim",
        expiration_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"name": token_name}
        if expiration_date:
            body["expirationDate"] = expiration_date
        data = await self.request(
            "POST",
            f"/v2/users/{user_id}/pats",
            json_body=body,
        )
        return {
            "token_id": data.get("tokenId"),
            "token": data.get("token"),
            "creation_date": data.get("creationDate"),
            "raw": data,
        }

    async def add_org_member(
        self,
        *,
        org_id: str,
        user_id: str,
        roles: list[str],
    ) -> Dict[str, Any]:
        data = await self.request(
            "POST",
            "/management/v1/orgs/me/members",
            json_body={
                "userId": user_id,
                "roles": roles,
            },
            org_id=org_id,
        )
        return {"raw": data}

    async def get_user_by_id(self, *, user_id: str) -> Dict[str, Any]:
        data = await self.request("GET", f"/v2/users/{quote(user_id, safe='')}")
        return {
            "user_id": data.get("id"),
            "resource_owner": data.get("details", {}).get("resourceOwner"),
            "user_name": data.get("userName"),
            "preferred_login_name": data.get("preferredLoginName"),
            "display_name": data.get("human", {}).get("profile", {}).get("displayName"),
            "email": data.get("human", {}).get("email", {}).get("email"),
            "raw": data,
        }

    async def search_users_by_email(
        self, *, email: str, org_id: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        data = await self.request(
            "POST",
            "/management/v1/users/_search",
            json_body={
                "queries": [
                    {
                        "emailQuery": {
                            "emailAddress": email,
                            "method": "TEXT_QUERY_METHOD_EQUALS",
                        }
                    }
                ]
            },
            org_id=org_id,
        )
        results = data.get("result") or []
        normalized: list[Dict[str, Any]] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "user_id": row.get("id"),
                    "resource_owner": row.get("details", {}).get("resourceOwner"),
                    "user_name": row.get("userName"),
                    "preferred_login_name": row.get("preferredLoginName"),
                    "display_name": row.get("human", {})
                    .get("profile", {})
                    .get("displayName"),
                    "raw": row,
                }
            )
        return normalized

    async def add_project_grant(
        self,
        *,
        project_id: str,
        granted_org_id: str,
        role_keys: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"grantedOrgId": granted_org_id}
        if role_keys:
            body["roleKeys"] = role_keys
        data = await self.request(
            "POST",
            f"/management/v1/projects/{project_id}/grants",
            json_body=body,
        )
        return {
            "grant_id": data.get("grantId"),
            "raw": data,
        }

    async def add_user_grant(
        self,
        *,
        user_id: str,
        project_id: str,
        role_keys: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"projectId": project_id}
        if role_keys:
            body["roleKeys"] = role_keys
        data = await self.request(
            "POST",
            f"/management/v1/users/{quote(user_id, safe='')}/grants",
            json_body=body,
        )
        return {
            "user_grant_id": data.get("userGrantId"),
            "raw": data,
        }

    async def search_org_domains(self, *, org_id: str) -> list[Dict[str, Any]]:
        data = await self.request(
            "POST",
            "/management/v1/orgs/me/domains/_search",
            json_body={},
            org_id=org_id,
        )
        results = data.get("result") or []
        return [dict(row) for row in results if isinstance(row, dict)]

    async def add_org_domain(self, *, org_id: str, domain: str) -> Dict[str, Any]:
        data = await self.request(
            "POST",
            "/management/v1/orgs/me/domains",
            json_body={"domain": domain},
            org_id=org_id,
        )
        return {"raw": data}

    async def delete_org_domain(self, *, org_id: str, domain: str) -> Dict[str, Any]:
        data = await self.request(
            "DELETE",
            f"/management/v1/orgs/me/domains/{quote(domain, safe='')}",
            org_id=org_id,
        )
        return {"raw": data}

    async def set_primary_org_domain(self, *, org_id: str, domain: str) -> Dict[str, Any]:
        data = await self.request(
            "POST",
            f"/management/v1/orgs/me/domains/{quote(domain, safe='')}/_set_primary",
            json_body={},
            org_id=org_id,
        )
        return {"raw": data}

    async def get_login_policy(self, *, org_id: str) -> Dict[str, Any]:
        data = await self.request(
            "GET",
            "/management/v1/policies/login",
            org_id=org_id,
        )
        return data.get("policy") or {}

    async def update_login_policy(
        self,
        *,
        org_id: str,
        allow_username_password: bool,
        allow_external_idp: bool,
        allow_register: bool,
        allow_domain_discovery: bool,
    ) -> Dict[str, Any]:
        data = await self.request(
            "PUT",
            "/management/v1/policies/login",
            json_body={
                "allowUsernamePassword": allow_username_password,
                "allowExternalIdp": allow_external_idp,
                "allowRegister": allow_register,
                "allowDomainDiscovery": allow_domain_discovery,
            },
            org_id=org_id,
        )
        return {"raw": data}

    async def add_org_oidc_provider(
        self,
        *,
        org_id: str,
        name: str,
        issuer: str,
        client_id: str,
        client_secret: str,
        scopes: list[str],
        username_mapping: str,
        display_name_mapping: str,
        auto_register: bool,
    ) -> Dict[str, Any]:
        data = await self.request(
            "POST",
            "/management/v1/idps/oidc",
            json_body={
                "name": name,
                "clientId": client_id,
                "clientSecret": client_secret,
                "issuer": issuer,
                "scopes": scopes,
                "usernameMapping": username_mapping,
                "displayNameMapping": display_name_mapping,
                "autoRegister": auto_register,
            },
            org_id=org_id,
        )
        return {
            "idp_id": data.get("idpId"),
            "raw": data,
        }

    async def add_idp_to_login_policy(
        self,
        *,
        org_id: str,
        idp_id: str,
    ) -> Dict[str, Any]:
        data = await self.request(
            "POST",
            "/management/v1/policies/login/idps",
            json_body={
                "idpId": idp_id,
                "ownerType": "IDP_OWNER_TYPE_ORG",
            },
            org_id=org_id,
        )
        return {"raw": data}
