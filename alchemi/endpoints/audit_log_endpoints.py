"""Audit log endpoints - query audit logs from database and OpenObserve."""
from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("/logs")
async def get_audit_logs(
    request: Request,
    table_name: Optional[str] = None,
    action: Optional[str] = None,
    changed_by: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get audit logs from database, filtered by account_id."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()

    where_conditions = {}
    if account_id:
        where_conditions["account_id"] = account_id
    if table_name:
        where_conditions["table_name"] = table_name
    if action:
        where_conditions["action"] = action
    if changed_by:
        where_conditions["changed_by"] = changed_by
    if start_date:
        where_conditions["updated_at"] = {"gte": datetime.fromisoformat(start_date)}
    if end_date:
        if "updated_at" in where_conditions:
            where_conditions["updated_at"]["lte"] = datetime.fromisoformat(end_date)
        else:
            where_conditions["updated_at"] = {"lte": datetime.fromisoformat(end_date)}

    logs = await prisma_client.db.litellm_auditlog.find_many(
        where=where_conditions,
        order={"updated_at": "desc"},
        take=limit,
        skip=offset,
    )
    total = await prisma_client.db.litellm_auditlog.count(where=where_conditions)

    return {"logs": logs, "total": total, "limit": limit, "offset": offset}


@router.get("/logs/openobserve")
async def get_openobserve_logs(
    request: Request,
    query: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(default=50, le=500),
):
    """Query audit logs from OpenObserve."""
    from alchemi.integrations.openobserve import OpenObserveClient
    from alchemi.middleware.tenant_context import get_current_account_id

    account_id = get_current_account_id()
    client = OpenObserveClient()

    if not client.is_configured():
        raise HTTPException(
            status_code=503,
            detail="OpenObserve is not configured.",
        )

    search_query = f'account_id="{account_id}"' if account_id else "*"
    if query:
        search_query = f"{search_query} AND ({query})"

    results = await client.search(
        query=search_query,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    return results
