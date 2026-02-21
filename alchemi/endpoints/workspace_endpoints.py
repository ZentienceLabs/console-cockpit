"""
Workspace management endpoints.
CRUD for workspaces and workspace member assignments,
scoped to the caller's account via tenant context.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/workspace", tags=["Workspaces"])


# ── Request Models ───────────────────────────────────────────────────────────


class WorkspaceCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    product_info: Optional[Dict[str, Any]] = None
    workspace_info: Optional[Dict[str, Any]] = None


class WorkspaceUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    product_info: Optional[Dict[str, Any]] = None
    workspace_info: Optional[Dict[str, Any]] = None
    analysis_data: Optional[Dict[str, Any]] = None
    current_analysis_state: Optional[str] = None
    is_mvp_ready: Optional[bool] = None


class WorkspaceMemberRequest(BaseModel):
    user_id: str
    role_id: Optional[str] = None


class WorkspaceMemberUpdateRequest(BaseModel):
    role_id: Optional[str] = None
    status: Optional[str] = None


# ── Workspace CRUD ───────────────────────────────────────────────────────────


@router.post("/new")
async def create_workspace(
    data: WorkspaceCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new workspace for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    workspace_id = str(uuid.uuid4())
    now = datetime.utcnow()

    workspace = await prisma_client.db.alchemi_workspacetable.create(
        data={
            "id": workspace_id,
            "account_id": account_id,
            "name": data.name,
            "description": data.description,
            "status": "ACTIVE",
            "is_mvp_ready": False,
            "product_info": Json(data.product_info or {}),
            "workspace_info": Json(data.workspace_info or {}),
            "analysis_data": Json({}),
            "created_by": account_id,
            "updated_by": account_id,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": workspace.id,
        "name": workspace.name,
        "status": workspace.status,
        "message": "Workspace created successfully",
    }


@router.get("/list")
async def list_workspaces(
    request: Request,
    status: Optional[str] = Query(default=None, description="Filter by status"),
    _=Depends(require_account_access),
):
    """List workspaces for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if status:
        where["status"] = status

    workspaces = await prisma_client.db.alchemi_workspacetable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"workspaces": workspaces}


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get workspace detail with members included."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    workspace = await prisma_client.db.alchemi_workspacetable.find_first(
        where={"id": workspace_id, "account_id": account_id},
        include={"members": True},
    )

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return workspace


@router.put("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a workspace."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_workspacetable.find_first(
        where={"id": workspace_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Workspace not found")

    update_data: Dict[str, Any] = {"updated_by": account_id, "updated_at": datetime.utcnow()}

    if data.name is not None:
        update_data["name"] = data.name
    if data.description is not None:
        update_data["description"] = data.description
    if data.status is not None:
        update_data["status"] = data.status
    if data.current_analysis_state is not None:
        update_data["current_analysis_state"] = data.current_analysis_state
    if data.is_mvp_ready is not None:
        update_data["is_mvp_ready"] = data.is_mvp_ready
    if data.product_info is not None:
        update_data["product_info"] = Json(data.product_info)
    if data.workspace_info is not None:
        update_data["workspace_info"] = Json(data.workspace_info)
    if data.analysis_data is not None:
        update_data["analysis_data"] = Json(data.analysis_data)

    workspace = await prisma_client.db.alchemi_workspacetable.update(
        where={"id": workspace_id},
        data=update_data,
    )

    return workspace


@router.delete("/{workspace_id}")
async def archive_workspace(
    workspace_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Archive a workspace (soft delete by setting status to ARCHIVED)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_workspacetable.find_first(
        where={"id": workspace_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Workspace not found")

    await prisma_client.db.alchemi_workspacetable.update(
        where={"id": workspace_id},
        data={
            "status": "ARCHIVED",
            "updated_by": account_id,
            "updated_at": datetime.utcnow(),
        },
    )

    return {
        "message": f"Workspace '{existing.name}' archived",
        "id": workspace_id,
    }


# ── Workspace Member Management ─────────────────────────────────────────────


@router.post("/{workspace_id}/member")
async def add_workspace_member(
    workspace_id: str,
    data: WorkspaceMemberRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Add a member to a workspace."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify workspace belongs to this account
    workspace = await prisma_client.db.alchemi_workspacetable.find_first(
        where={"id": workspace_id, "account_id": account_id},
    )
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check for duplicate membership
    existing_member = await prisma_client.db.alchemi_workspacemembertable.find_first(
        where={"workspace_id": workspace_id, "user_id": data.user_id},
    )
    if existing_member:
        raise HTTPException(
            status_code=400,
            detail="User is already a member of this workspace",
        )

    now = datetime.utcnow()
    member = await prisma_client.db.alchemi_workspacemembertable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "workspace_id": workspace_id,
            "user_id": data.user_id,
            "role_id": data.role_id,
            "status": "ACTIVE",
            "created_by": account_id,
            "updated_by": account_id,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": member.id,
        "workspace_id": member.workspace_id,
        "user_id": member.user_id,
        "message": "Member added successfully",
    }


@router.get("/{workspace_id}/member/list")
async def list_workspace_members(
    workspace_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """List members of a workspace."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify workspace belongs to this account
    workspace = await prisma_client.db.alchemi_workspacetable.find_first(
        where={"id": workspace_id, "account_id": account_id},
    )
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    members = await prisma_client.db.alchemi_workspacemembertable.find_many(
        where={"workspace_id": workspace_id, "account_id": account_id},
        order={"created_at": "desc"},
    )

    return {"members": members}


@router.put("/{workspace_id}/member/{member_id}")
async def update_workspace_member(
    workspace_id: str,
    member_id: str,
    data: WorkspaceMemberUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a workspace member's role or status."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify member belongs to this workspace and account
    existing = await prisma_client.db.alchemi_workspacemembertable.find_first(
        where={
            "id": member_id,
            "workspace_id": workspace_id,
            "account_id": account_id,
        },
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Member not found")

    update_data: Dict[str, Any] = {"updated_by": account_id, "updated_at": datetime.utcnow()}

    if data.role_id is not None:
        update_data["role_id"] = data.role_id
    if data.status is not None:
        update_data["status"] = data.status

    member = await prisma_client.db.alchemi_workspacemembertable.update(
        where={"id": member_id},
        data=update_data,
    )

    return member


@router.delete("/{workspace_id}/member/{member_id}")
async def remove_workspace_member(
    workspace_id: str,
    member_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Remove a member from a workspace."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify member belongs to this workspace and account
    existing = await prisma_client.db.alchemi_workspacemembertable.find_first(
        where={
            "id": member_id,
            "workspace_id": workspace_id,
            "account_id": account_id,
        },
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Member not found")

    await prisma_client.db.alchemi_workspacemembertable.delete(
        where={"id": member_id},
    )

    return {
        "message": "Member removed from workspace",
        "id": member_id,
        "workspace_id": workspace_id,
    }
