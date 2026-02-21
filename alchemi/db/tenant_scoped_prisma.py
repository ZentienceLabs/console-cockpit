"""
Tenant-scoped Prisma wrapper that auto-injects account_id filtering.

This is the core multi-tenancy mechanism. It wraps each Prisma table model
to automatically add WHERE account_id = ? filters on queries and set
account_id on creates. Super admins bypass filtering.
"""
from typing import Any, Optional, List, Set
from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin


# Tables that should be scoped by account_id
TENANT_SCOPED_TABLES: Set[str] = {
    "alchemi_accounttable",
    "alchemi_accountadmintable",
    "alchemi_accountssoconfig",
    "litellm_organizationtable",
    "litellm_teamtable",
    "litellm_usertable",
    "litellm_verificationtoken",
    "litellm_budgettable",
    "litellm_proxymodeltable",
    "litellm_agentstable",
    "litellm_mcpservertable",
    "litellm_guardrailstable",
    "litellm_policytable",
    "litellm_policyattachmenttable",
    "litellm_accessgrouptable",
    "litellm_credentialstable",
    "litellm_config",
    "litellm_spendlogs",
    "litellm_auditlog",
    "litellm_dailyuserspend",
    "litellm_dailyteamspend",
    "litellm_dailyorganizationspend",
    "litellm_dailyenduserspend",
    "litellm_dailyagentspend",
    "litellm_dailytagspend",
    "litellm_errorlogs",
    "litellm_tagtable",
    "litellm_endusertable",
    "litellm_invitationlink",
    "litellm_teammembership",
    "litellm_organizationmembership",
    "litellm_objectpermissiontable",
    "litellm_deletedteamtable",
    "litellm_deletedverificationtoken",
    "litellm_healthchecktable",
    "litellm_prompttable",
    "litellm_searchtoolstable",
    "litellm_skillstable",
    # Centralized Platform - Subscriptions & Quotas
    "alchemi_subscriptiontable",
    "alchemi_accountmembershiptable",
    "alchemi_accountquotatable",
    # Centralized Platform - Roles & Permissions
    "alchemi_roletable",
    "alchemi_rolepermissiontable",
    # Centralized Platform - Workspaces
    "alchemi_workspacetable",
    "alchemi_workspacemembertable",
    # Centralized Platform - Agent Registry
    "alchemi_agentdeftable",
    "alchemi_agentgrouptable",
    "alchemi_agentgroupmembertable",
    "alchemi_agentmarketplacetable",
    # Centralized Platform - Guardrails
    "alchemi_guardrailsconfigtable",
    "alchemi_guardrailscustompatterntable",
    "alchemi_guardrailsauditlogtable",
    # Centralized Platform - Configuration
    "alchemi_configprovidertable",
    "alchemi_configmodeltable",
    "alchemi_configdefaultmodeltable",
    "alchemi_configsandboxpricingtable",
    # Centralized Platform - Integrations & Connections
    "alchemi_connectiontable",
    "alchemi_integrationconnectiontable",
    "alchemi_mcpconfigtable",
    "alchemi_mvpconfigtable",
    # Centralized Platform - Financial
    "alchemi_budgetplantable",
    "alchemi_creditbudgettable",
    "alchemi_costtrackingtable",
    # Centralized Platform - Override Configs
    "alchemi_accountoverrideconfigtable",
    # Centralized Platform - Communication & Support
    "alchemi_notificationtable",
    "alchemi_accountnotificationtemplatetable",
    "alchemi_discussiontable",
    "alchemi_userinvitetable",
    "alchemi_supporttickettable",
    "alchemi_accesstokentable",
}

# Account tables should NOT be filtered (super admin manages these)
ACCOUNT_MANAGEMENT_TABLES: Set[str] = {
    "alchemi_accounttable",
    "alchemi_accountadmintable",
    "alchemi_accountssoconfig",
}


class TenantScopedModel:
    """
    Wraps a Prisma model to auto-inject account_id in WHERE clauses.
    For find/count/delete: adds account_id to where conditions.
    For create/upsert: adds account_id to data.
    Super admins bypass all filtering.
    """

    def __init__(self, original_model: Any, table_name: str):
        self._original = original_model
        self._table_name = table_name.lower()
        self._is_scoped = self._table_name in TENANT_SCOPED_TABLES
        self._is_account_table = self._table_name in ACCOUNT_MANAGEMENT_TABLES

    def _should_scope(self) -> bool:
        """Determine if this query should be scoped by account_id."""
        if not self._is_scoped:
            return False
        if is_super_admin():
            return False
        if self._is_account_table:
            return False
        account_id = get_current_account_id()
        return account_id is not None

    def _get_account_id(self) -> Optional[str]:
        return get_current_account_id()

    def _inject_where(self, where: Any = None) -> Any:
        """Inject account_id into where conditions."""
        if not self._should_scope():
            return where

        account_id = self._get_account_id()
        if account_id is None:
            return where

        if where is None:
            return {"account_id": account_id}

        if isinstance(where, dict):
            where_copy = dict(where)
            if "account_id" not in where_copy:
                where_copy["account_id"] = account_id
            return where_copy

        return where

    def _inject_data(self, data: Any) -> Any:
        """Inject account_id into create/update data."""
        if not self._is_scoped or self._is_account_table:
            return data
        if is_super_admin():
            return data

        account_id = self._get_account_id()
        if account_id is None:
            return data

        if isinstance(data, dict):
            data_copy = dict(data)
            if "account_id" not in data_copy:
                data_copy["account_id"] = account_id
            return data_copy

        return data

    async def find_many(self, *args, **kwargs) -> Any:
        if "where" in kwargs:
            kwargs["where"] = self._inject_where(kwargs["where"])
        elif not args:
            kwargs["where"] = self._inject_where(None)
        return await self._original.find_many(*args, **kwargs)

    async def find_first(self, *args, **kwargs) -> Any:
        if "where" in kwargs:
            kwargs["where"] = self._inject_where(kwargs["where"])
        elif not args:
            kwargs["where"] = self._inject_where(None)
        return await self._original.find_first(*args, **kwargs)

    async def find_unique(self, *args, **kwargs) -> Any:
        # find_unique uses primary key, don't inject account_id filter
        # but we validate after fetch
        result = await self._original.find_unique(*args, **kwargs)
        if result and self._should_scope():
            account_id = self._get_account_id()
            result_account = getattr(result, "account_id", None)
            if account_id and result_account and result_account != account_id:
                return None  # Not in this tenant's scope
        return result

    async def find_unique_or_raise(self, *args, **kwargs) -> Any:
        result = await self._original.find_unique_or_raise(*args, **kwargs)
        if result and self._should_scope():
            account_id = self._get_account_id()
            result_account = getattr(result, "account_id", None)
            if account_id and result_account and result_account != account_id:
                raise Exception("Record not found in tenant scope")
        return result

    async def create(self, *args, **kwargs) -> Any:
        if "data" in kwargs:
            kwargs["data"] = self._inject_data(kwargs["data"])
        return await self._original.create(*args, **kwargs)

    async def create_many(self, *args, **kwargs) -> Any:
        if "data" in kwargs and isinstance(kwargs["data"], list):
            kwargs["data"] = [self._inject_data(d) for d in kwargs["data"]]
        return await self._original.create_many(*args, **kwargs)

    async def update(self, *args, **kwargs) -> Any:
        # Validate the record belongs to current tenant before updating
        if self._should_scope() and "where" in kwargs:
            account_id = self._get_account_id()
            if account_id:
                record = await self._original.find_unique(where=kwargs["where"])
                if record:
                    record_account = getattr(record, "account_id", None)
                    if record_account and record_account != account_id:
                        raise Exception("Cannot update record outside tenant scope")
        return await self._original.update(*args, **kwargs)

    async def update_many(self, *args, **kwargs) -> Any:
        if "where" in kwargs:
            kwargs["where"] = self._inject_where(kwargs["where"])
        return await self._original.update_many(*args, **kwargs)

    async def upsert(self, *args, **kwargs) -> Any:
        if "where" in kwargs:
            kwargs["where"] = self._inject_where(kwargs["where"])
        # Prisma Python client nests create/update inside a "data" dict:
        #   upsert(where={...}, data={"create": {...}, "update": {...}})
        # account_id is only injected into "create"; "update" doesn't need it
        # because the where clause is already scoped to the current tenant.
        if "data" in kwargs and isinstance(kwargs["data"], dict):
            if "create" in kwargs["data"]:
                kwargs["data"]["create"] = self._inject_data(kwargs["data"]["create"])
        return await self._original.upsert(*args, **kwargs)

    async def delete(self, *args, **kwargs) -> Any:
        # Validate the record belongs to current tenant before deleting
        if self._should_scope() and "where" in kwargs:
            account_id = self._get_account_id()
            if account_id:
                record = await self._original.find_unique(where=kwargs["where"])
                if record:
                    record_account = getattr(record, "account_id", None)
                    if record_account and record_account != account_id:
                        raise Exception("Cannot delete record outside tenant scope")
        return await self._original.delete(*args, **kwargs)

    async def delete_many(self, *args, **kwargs) -> Any:
        if "where" in kwargs:
            kwargs["where"] = self._inject_where(kwargs["where"])
        return await self._original.delete_many(*args, **kwargs)

    async def count(self, *args, **kwargs) -> int:
        if "where" in kwargs:
            kwargs["where"] = self._inject_where(kwargs["where"])
        elif not args:
            kwargs["where"] = self._inject_where(None)
        return await self._original.count(*args, **kwargs)

    async def group_by(self, *args, **kwargs) -> Any:
        if "where" in kwargs:
            kwargs["where"] = self._inject_where(kwargs["where"])
        return await self._original.group_by(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Proxy any other attribute access to the original model."""
        return getattr(self._original, name)


class TenantScopedPrismaClient:
    """
    Wraps a Prisma client to provide tenant-scoped access to all tables.
    Usage: prisma_client.db = TenantScopedPrismaClient(prisma_client.db)
    """

    def __init__(self, original_client: Any):
        self._original = original_client
        self._wrapped_models = {}

    def __getattr__(self, name: str) -> Any:
        """
        Intercept attribute access to wrap table models with TenantScopedModel.
        Caches wrapped models for performance.
        """
        # Check if this is a table model that should be wrapped
        table_name = name.lower()
        if table_name in TENANT_SCOPED_TABLES:
            if name not in self._wrapped_models:
                original_model = getattr(self._original, name)
                self._wrapped_models[name] = TenantScopedModel(
                    original_model, table_name
                )
            return self._wrapped_models[name]

        # For non-scoped attributes, pass through to original client
        return getattr(self._original, name)
