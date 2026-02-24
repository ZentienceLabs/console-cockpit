"""
Async PostgreSQL client for the copilot schema.
Uses asyncpg for direct SQL access to copilot.* tables,
auto-injecting account_id for tenant scoping.

Mirrors the TenantScopedPrismaClient pattern but uses asyncpg
since Prisma doesn't natively support multiple PostgreSQL schemas.
"""
import os
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import asyncpg

from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

_pool: Optional[asyncpg.Pool] = None

# Prisma-specific query params that asyncpg doesn't understand
_PRISMA_ONLY_PARAMS = {"connection_limit", "pool_timeout", "connect_timeout", "schema", "sslaccept", "pgbouncer"}


def _clean_dsn(dsn: str) -> str:
    """Strip Prisma-specific query parameters from a DATABASE_URL."""
    parsed = urlparse(dsn)
    if not parsed.query:
        return dsn
    params = parse_qs(parsed.query)
    cleaned = {k: v for k, v in params.items() if k not in _PRISMA_ONLY_PARAMS}
    new_query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        dsn = _clean_dsn(os.getenv("DATABASE_URL", ""))
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _serialize_value(value: Any) -> Any:
    """Serialize Python values for asyncpg.

    - Dicts are serialized to JSON strings (for JSONB columns).
    - Lists are serialized to JSON strings (for JSONB columns).
    - uuid.UUID is converted to str.

    Note: For PostgreSQL array columns (TEXT[], UUID[]), callers must wrap
    values in PgArray() to prevent JSON serialization.
    """
    if isinstance(value, PgArray):
        return value.values
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


class PgArray:
    """Wrapper to indicate a value should be passed as a PostgreSQL array, not JSONB."""
    def __init__(self, values: list):
        self.values = values


def _deserialize_row(row: asyncpg.Record) -> Dict[str, Any]:
    """Convert an asyncpg Record to a dict with JSON-safe types."""
    result = {}
    for key, value in dict(row).items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = float(value)
        elif isinstance(value, uuid.UUID):
            result[key] = str(value)
        else:
            result[key] = value
    return result


class CopilotDB:
    """
    Tenant-scoped query builder for copilot schema tables.
    Auto-injects WHERE account_id = ? for non-super-admin requests.
    """

    def __init__(self, table: str, id_column: str = "id", has_account_id: bool = True):
        self.table = f"copilot.{table}"
        self.id_column = id_column
        self.has_account_id = has_account_id

    def _get_account_filter(self) -> Optional[str]:
        """Return account_id for filtering, or None if super admin or table has no account_id."""
        if not self.has_account_id:
            return None
        if is_super_admin():
            return None
        return get_current_account_id()

    def _build_where(
        self, where: Optional[Dict] = None, param_offset: int = 0
    ) -> Tuple[str, List[Any]]:
        """Build WHERE clause with tenant scoping."""
        conditions = []
        params = []
        idx = param_offset + 1

        account_id = self._get_account_filter()
        if account_id:
            conditions.append(f"account_id = ${idx}")
            params.append(account_id)
            idx += 1

        if where:
            for key, value in where.items():
                if value is None:
                    conditions.append(f"{key} IS NULL")
                else:
                    conditions.append(f"{key} = ${idx}")
                    params.append(_serialize_value(value))
                    idx += 1

        clause = " AND ".join(conditions) if conditions else ""
        return clause, params

    async def find_many(
        self,
        where: Optional[Dict] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Find multiple records with tenant scoping."""
        pool = await get_pool()
        clause, params = self._build_where(where)

        query = f"SELECT * FROM {self.table}"
        if clause:
            query += f" WHERE {clause}"
        if order_by:
            query += f" ORDER BY {order_by}"
        if limit is not None:
            params.append(limit)
            query += f" LIMIT ${len(params)}"
        if offset is not None:
            params.append(offset)
            query += f" OFFSET ${len(params)}"

        rows = await pool.fetch(query, *params)
        return [_deserialize_row(r) for r in rows]

    async def find_by_id(self, id_value: str) -> Optional[Dict[str, Any]]:
        """Find a single record by ID with tenant scoping."""
        pool = await get_pool()
        account_id = self._get_account_filter()

        query = f"SELECT * FROM {self.table} WHERE {self.id_column} = $1"
        params: List[Any] = [id_value]

        if account_id:
            query += " AND account_id = $2"
            params.append(account_id)

        row = await pool.fetchrow(query, *params)
        return _deserialize_row(row) if row else None

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a record with auto-injected account_id."""
        pool = await get_pool()
        account_id = self._get_account_filter()

        # Auto-inject account_id if not provided
        if account_id and "account_id" not in data:
            data["account_id"] = account_id

        # Generate ID if not provided
        if self.id_column not in data:
            data[self.id_column] = str(uuid.uuid4())

        cols = list(data.keys())
        vals = [_serialize_value(v) for v in data.values()]
        placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
        col_names = ", ".join(f'"{c}"' if c != c.lower() else c for c in cols)

        query = f"INSERT INTO {self.table} ({col_names}) VALUES ({placeholders}) RETURNING *"
        row = await pool.fetchrow(query, *vals)
        return _deserialize_row(row)

    async def update(
        self, id_value: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a record by ID with tenant scoping."""
        pool = await get_pool()
        account_id = self._get_account_filter()

        # Add updated_at timestamp
        data["updated_at"] = datetime.utcnow()

        set_clauses = []
        params: List[Any] = []
        for i, (key, value) in enumerate(data.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            params.append(_serialize_value(value))

        idx = len(params) + 1
        params.append(id_value)
        query = f"UPDATE {self.table} SET {', '.join(set_clauses)} WHERE {self.id_column} = ${idx}"

        if account_id:
            idx += 1
            params.append(account_id)
            query += f" AND account_id = ${idx}"

        query += " RETURNING *"
        row = await pool.fetchrow(query, *params)
        return _deserialize_row(row) if row else None

    async def delete(self, id_value: str) -> bool:
        """Delete a record by ID with tenant scoping."""
        pool = await get_pool()
        account_id = self._get_account_filter()

        query = f"DELETE FROM {self.table} WHERE {self.id_column} = $1"
        params: List[Any] = [id_value]

        if account_id:
            query += " AND account_id = $2"
            params.append(account_id)

        result = await pool.execute(query, *params)
        return result.endswith("1")

    async def count(self, where: Optional[Dict] = None) -> int:
        """Count records with tenant scoping."""
        pool = await get_pool()
        clause, params = self._build_where(where)

        query = f"SELECT COUNT(*) FROM {self.table}"
        if clause:
            query += f" WHERE {clause}"

        return await pool.fetchval(query, *params)

    async def execute_raw(self, query: str, *params) -> List[Dict[str, Any]]:
        """Execute a raw SQL query (for views, aggregations, etc.)."""
        pool = await get_pool()
        rows = await pool.fetch(query, *params)
        return [_deserialize_row(r) for r in rows]

    async def execute_raw_val(self, query: str, *params) -> Any:
        """Execute a raw SQL query and return a single value."""
        pool = await get_pool()
        return await pool.fetchval(query, *params)

    async def atomic_increment(
        self,
        id_value: str,
        field: str,
        amount: int,
        max_field: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically increment a field, optionally bounded by a max field.
        Returns the updated row or None if the increment would exceed max.
        """
        pool = await get_pool()
        account_id = self._get_account_filter()

        if max_field:
            query = (
                f"UPDATE {self.table} SET {field} = {field} + $1, updated_at = now() "
                f"WHERE {self.id_column} = $2 AND {field} + $1 <= {max_field}"
            )
        else:
            query = (
                f"UPDATE {self.table} SET {field} = {field} + $1, updated_at = now() "
                f"WHERE {self.id_column} = $2"
            )

        params: List[Any] = [amount, id_value]

        if account_id:
            query += f" AND account_id = ${len(params) + 1}"
            params.append(account_id)

        query += " RETURNING *"
        row = await pool.fetchrow(query, *params)
        return _deserialize_row(row) if row else None


# ============================================
# Pre-built table accessors
# ============================================
credit_budgets = CopilotDB("credit_budget")
budget_plans = CopilotDB("budget_plans")
agents_def = CopilotDB("agents_def", id_column="agent_id")
agent_groups = CopilotDB("agent_groups")
agent_group_members = CopilotDB("agent_group_members", has_account_id=False)
marketplace_items = CopilotDB("marketplace_items", id_column="marketplace_id")
account_connections = CopilotDB("account_connections")
guardrails_config = CopilotDB("guardrails_config")
guardrails_custom_patterns = CopilotDB("guardrails_custom_patterns")
guardrails_audit_log = CopilotDB("guardrails_audit_log")
users = CopilotDB("users")
account_memberships = CopilotDB("account_memberships")
groups = CopilotDB("groups")
teams = CopilotDB("teams")
user_invites = CopilotDB("user_invites")
notification_templates = CopilotDB("notification_templates")
support_tickets = CopilotDB("support_tickets")
model_catalog = CopilotDB("model_catalog", has_account_id=False)
integration_catalog = CopilotDB("integration_catalog", has_account_id=False)
audit_log = CopilotDB("audit_log")
