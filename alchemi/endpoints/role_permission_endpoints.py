"""
Role and permission management endpoints.
CRUD for roles (account-scoped) and permissions (platform-wide).
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid

from alchemi.auth.service_auth import require_account_access, require_super_admin

router = APIRouter(prefix="/alchemi/role", tags=["Roles & Permissions"])


# -- Request Models -----------------------------------------------------------


class RoleCreateRequest(BaseModel):
    name: str
    type: Optional[str] = None
    provider: Optional[str] = "PLATFORM"
    is_default: Optional[bool] = False


class RoleUpdateRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    is_default: Optional[bool] = None


class PermissionCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    subject: str
    action: str
    is_system_permission: Optional[bool] = False
    fields: Optional[List[str]] = None
    conditions: Optional[str] = None


class RolePermissionAssignRequest(BaseModel):
    permission_id: str


# -- Permission Routes (before /{role_id} to avoid path conflicts) -----------


@router.get("/permission/list")
async def list_permissions(
    request: Request,
    subject: Optional[str] = Query(default=None, description="Filter by subject"),
    action: Optional[str] = Query(default=None, description="Filter by action"),
    _=Depends(require_account_access),
):
    """List all permissions (platform-wide)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    where: Dict[str, Any] = {}
    if subject:
        where["subject"] = subject
    if action:
        where["action"] = action

    permissions = await prisma_client.db.alchemi_permissiontable.find_many(
        where=where if where else None,
        order={"name": "asc"},
    )

    return {"permissions": permissions}


@router.post("/permission/new")
async def create_permission(
    data: PermissionCreateRequest,
    request: Request,
    _=Depends(require_super_admin),
):
    """Create a new permission (super_admin only)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    permission_id = str(uuid.uuid4())

    create_data: Dict[str, Any] = {
        "id": permission_id,
        "name": data.name,
        "subject": data.subject,
        "action": data.action,
        "is_system_permission": data.is_system_permission or False,
    }

    if data.description is not None:
        create_data["description"] = data.description
    if data.fields is not None:
        create_data["fields"] = data.fields
    if data.conditions is not None:
        create_data["conditions"] = data.conditions

    permission = await prisma_client.db.alchemi_permissiontable.create(
        data=create_data,
    )

    return {
        "id": permission.id,
        "name": permission.name,
        "message": "Permission created successfully",
    }


# -- Role Routes --------------------------------------------------------------


@router.post("/new")
async def create_role(
    data: RoleCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new role for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Check for duplicate name within account
    existing = await prisma_client.db.alchemi_roletable.find_first(
        where={"account_id": account_id, "name": data.name, "is_deleted": False},
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Role '{data.name}' already exists in this account",
        )

    role_id = str(uuid.uuid4())

    create_data: Dict[str, Any] = {
        "id": role_id,
        "account_id": account_id,
        "name": data.name,
        "provider": data.provider or "PLATFORM",
        "is_default": data.is_default or False,
        "is_deleted": False,
    }

    if data.type is not None:
        create_data["type"] = data.type

    role = await prisma_client.db.alchemi_roletable.create(data=create_data)

    return {
        "id": role.id,
        "name": role.name,
        "message": "Role created successfully",
    }


@router.get("/list")
async def list_roles(
    request: Request,
    provider: Optional[str] = Query(default=None, description="Filter by provider"),
    is_default: Optional[bool] = Query(default=None, description="Filter by default flag"),
    _=Depends(require_account_access),
):
    """List roles for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id, "is_deleted": False}
    if provider:
        where["provider"] = provider
    if is_default is not None:
        where["is_default"] = is_default

    roles = await prisma_client.db.alchemi_roletable.find_many(
        where=where,
        order={"name": "asc"},
    )

    return {"roles": roles}


@router.get("/{role_id}")
async def get_role(
    role_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get role detail with its assigned permissions."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    role = await prisma_client.db.alchemi_roletable.find_first(
        where={"id": role_id, "account_id": account_id, "is_deleted": False},
    )

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Fetch assigned permissions
    role_permissions = await prisma_client.db.alchemi_rolepermissiontable.find_many(
        where={"role_id": role_id},
    )

    permission_ids = [rp.permission_id for rp in role_permissions]
    permissions = []
    if permission_ids:
        permissions = await prisma_client.db.alchemi_permissiontable.find_many(
            where={"id": {"in": permission_ids}},
        )

    return {
        "role": role,
        "permissions": permissions,
    }


@router.put("/{role_id}")
async def update_role(
    role_id: str,
    data: RoleUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a role."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_roletable.find_first(
        where={"id": role_id, "account_id": account_id, "is_deleted": False},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Role not found")

    update_data: Dict[str, Any] = {}

    if data.name is not None:
        # Check for name conflict
        conflict = await prisma_client.db.alchemi_roletable.find_first(
            where={
                "account_id": account_id,
                "name": data.name,
                "is_deleted": False,
                "id": {"not": role_id},
            },
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Role '{data.name}' already exists in this account",
            )
        update_data["name"] = data.name
    if data.type is not None:
        update_data["type"] = data.type
    if data.is_default is not None:
        update_data["is_default"] = data.is_default

    role = await prisma_client.db.alchemi_roletable.update(
        where={"id": role_id},
        data=update_data,
    )

    return role


@router.delete("/{role_id}")
async def delete_role(
    role_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Soft-delete a role (set is_deleted=True)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_roletable.find_first(
        where={"id": role_id, "account_id": account_id, "is_deleted": False},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Role not found")

    await prisma_client.db.alchemi_roletable.update(
        where={"id": role_id},
        data={"is_deleted": True},
    )

    return {
        "message": f"Role '{existing.name}' deleted",
        "id": role_id,
    }


# -- Role-Permission Assignment Routes ---------------------------------------


@router.post("/{role_id}/permission")
async def assign_permission_to_role(
    role_id: str,
    data: RolePermissionAssignRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Assign a permission to a role."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify role belongs to account
    role = await prisma_client.db.alchemi_roletable.find_first(
        where={"id": role_id, "account_id": account_id, "is_deleted": False},
    )
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Verify permission exists
    permission = await prisma_client.db.alchemi_permissiontable.find_unique(
        where={"id": data.permission_id},
    )
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")

    # Check for duplicate assignment
    existing = await prisma_client.db.alchemi_rolepermissiontable.find_first(
        where={"role_id": role_id, "permission_id": data.permission_id},
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Permission already assigned to this role",
        )

    rp_id = str(uuid.uuid4())
    role_permission = await prisma_client.db.alchemi_rolepermissiontable.create(
        data={
            "id": rp_id,
            "role_id": role_id,
            "permission_id": data.permission_id,
        },
    )

    return {
        "id": role_permission.id,
        "role_id": role_id,
        "permission_id": data.permission_id,
        "message": "Permission assigned to role",
    }


@router.delete("/{role_id}/permission/{permission_id}")
async def remove_permission_from_role(
    role_id: str,
    permission_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Remove a permission from a role."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify role belongs to account
    role = await prisma_client.db.alchemi_roletable.find_first(
        where={"id": role_id, "account_id": account_id, "is_deleted": False},
    )
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Find the assignment
    rp = await prisma_client.db.alchemi_rolepermissiontable.find_first(
        where={"role_id": role_id, "permission_id": permission_id},
    )
    if not rp:
        raise HTTPException(
            status_code=404,
            detail="Permission not assigned to this role",
        )

    await prisma_client.db.alchemi_rolepermissiontable.delete(
        where={"id": rp.id},
    )

    return {
        "message": "Permission removed from role",
        "role_id": role_id,
        "permission_id": permission_id,
    }
