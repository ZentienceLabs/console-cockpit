"""
Agent definition and agent group management endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_auth import require_copilot_admin_access
from alchemi.endpoints.copilot_types import (
    AgentDefCreate,
    AgentDefUpdate,
    AgentGroupCreate,
    AgentGroupMemberAdd,
    AgentGroupUpdate,
)

router = APIRouter(prefix="/copilot/agents", tags=["Copilot - Agents"])


def _resolve_optional_account_filter(account_id: Optional[str]) -> Optional[str]:
    from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

    if is_super_admin():
        if account_id:
            return account_id
        return get_current_account_id()

    resolved = get_current_account_id()
    if not resolved:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    return resolved


def _resolve_required_account_for_write(account_id: Optional[str]) -> str:
    resolved = _resolve_optional_account_filter(account_id)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="account_id is required for this super admin write operation.",
        )
    return resolved


# ============================================
# Agent Definitions - List & Create
# ============================================

@router.get("/")
async def list_agents(
    request: Request,
    account_id: Optional[str] = None,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_admin_access),
):
    """List agent definitions."""
    where = {}
    resolved_account_id = _resolve_optional_account_filter(account_id)
    if resolved_account_id:
        where["account_id"] = resolved_account_id
    if status:
        where["status"] = status
    if provider:
        where["provider"] = provider

    agents = await copilot_db.agents_def.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.agents_def.count(where=where if where else None)
    return {"data": agents, "total": total}


@router.post("/")
async def create_agent(
    data: AgentDefCreate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Create a new agent definition."""
    from alchemi.db.copilot_db import PgArray

    create_data = data.model_dump()
    create_data["account_id"] = _resolve_required_account_for_write(account_id)
    # Wrap PostgreSQL array columns with PgArray to prevent JSON serialization
    for array_col in ("tags", "builtin_tools", "tools_mcp_ids", "tools_openapi_ids", "availability"):
        if array_col in create_data:
            create_data[array_col] = PgArray(create_data[array_col])

    agent = await copilot_db.agents_def.create(
        data=create_data
    )
    return {"data": agent}


# ============================================
# Agent Groups (fixed-path, before /{agent_id})
# ============================================

@router.get("/groups")
async def list_groups(
    request: Request,
    account_id: Optional[str] = None,
    group_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_admin_access),
):
    """List agent groups."""
    where = {}
    resolved_account_id = _resolve_optional_account_filter(account_id)
    if resolved_account_id:
        where["account_id"] = resolved_account_id
    if group_type:
        where["group_type"] = group_type
    if status:
        where["status"] = status

    groups = await copilot_db.agent_groups.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.agent_groups.count(where=where if where else None)
    return {"data": groups, "total": total}


@router.post("/groups")
async def create_group(
    data: AgentGroupCreate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Create a new agent group."""
    group = await copilot_db.agent_groups.create(
        data={
            **data.model_dump(),
            "account_id": _resolve_required_account_for_write(account_id),
        }
    )
    return {"data": group}


@router.put("/groups/{group_id}")
async def update_group(
    group_id: str,
    data: AgentGroupUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Update an agent group."""
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    group = await copilot_db.agent_groups.update(group_id, update_data)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    return {"data": group}


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete an agent group (cascades to members)."""
    deleted = await copilot_db.agent_groups.delete(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found.")
    return {"status": "ok"}


@router.post("/groups/{group_id}/members")
async def add_group_member(
    group_id: str,
    data: AgentGroupMemberAdd,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Add an agent to a group."""
    # Verify group exists
    group = await copilot_db.agent_groups.find_by_id(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")

    member = await copilot_db.agent_group_members.create(
        data={
            "group_id": group_id,
            "agent_id": data.agent_id,
            "display_order": data.display_order,
            "metadata": data.metadata,
        }
    )
    return {"data": member}


@router.delete("/groups/{group_id}/members/{agent_id}")
async def remove_group_member(
    group_id: str,
    agent_id: str,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Remove an agent from a group."""
    from alchemi.db.copilot_db import get_pool

    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM copilot.agent_group_members WHERE group_id = $1 AND agent_id = $2",
        group_id,
        agent_id,
    )
    if not result.endswith("1"):
        raise HTTPException(status_code=404, detail="Member not found.")
    return {"status": "ok"}


# ============================================
# Single Agent CRUD (dynamic path, must be last)
# ============================================

@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Get a single agent definition."""
    agent = await copilot_db.agents_def.find_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return {"data": agent}


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str,
    data: AgentDefUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Update an agent definition."""
    from alchemi.db.copilot_db import PgArray

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    # Wrap PostgreSQL array columns with PgArray
    for array_col in ("tags", "builtin_tools", "tools_mcp_ids", "tools_openapi_ids", "availability"):
        if array_col in update_data:
            update_data[array_col] = PgArray(update_data[array_col])

    agent = await copilot_db.agents_def.update(agent_id, update_data)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return {"data": agent}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete an agent definition."""
    deleted = await copilot_db.agents_def.delete(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return {"status": "ok"}
