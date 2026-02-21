"""
Cost tracking endpoints.
Records cost events from client services (alchemi-ai, alchemi-web) and
provides aggregated cost queries by workspace, user, account, and daily breakdown.
"""
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
from datetime import datetime, timedelta

from alchemi.auth.service_auth import require_scope, get_request_context

router = APIRouter(prefix="/v2/costs", tags=["Cost Tracking"])


# ── Request / Response Models ────────────────────────────────────────────────


class CostRecordRequest(BaseModel):
    workspace_id: str
    user_id: str
    model: str
    tool: str = "llm"
    cost: float
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    thread_id: Optional[str] = None


class CostBatchRequest(BaseModel):
    events: List[CostRecordRequest]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_date(value: Optional[str], default: Optional[datetime] = None) -> Optional[datetime]:
    """Parse an ISO date string, returning default if None."""
    if value is None:
        return default
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return default


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/record")
async def record_cost(
    data: CostRecordRequest,
    request: Request,
    _=require_scope("costs:write"),
):
    """Record a single cost event."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    record = await prisma_client.db.alchemi_costtrackingtable.create(
        data={
            "account_id": account_id,
            "workspace_id": data.workspace_id,
            "user_id": data.user_id,
            "model": data.model,
            "tool": data.tool,
            "cost": data.cost,
            "prompt_tokens": data.prompt_tokens,
            "completion_tokens": data.completion_tokens,
            "total_tokens": data.total_tokens,
            "metadata": Json(data.metadata) if data.metadata else None,
            "thread_id": data.thread_id,
        }
    )

    return {
        "id": record.id,
        "cost": record.cost,
        "message": "Cost recorded successfully",
    }


@router.post("/record/batch")
async def record_cost_batch(
    data: CostBatchRequest,
    request: Request,
    _=require_scope("costs:write"),
):
    """Batch record multiple cost events."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    record_ids = []
    for event in data.events:
        record = await prisma_client.db.alchemi_costtrackingtable.create(
            data={
                "account_id": account_id,
                "workspace_id": event.workspace_id,
                "user_id": event.user_id,
                "model": event.model,
                "tool": event.tool,
                "cost": event.cost,
                "prompt_tokens": event.prompt_tokens,
                "completion_tokens": event.completion_tokens,
                "total_tokens": event.total_tokens,
                "metadata": Json(event.metadata) if event.metadata else None,
                "thread_id": event.thread_id,
            }
        )
        record_ids.append(record.id)

    return {
        "recorded": len(record_ids),
        "ids": record_ids,
        "message": f"Batch recorded {len(record_ids)} cost events",
    }


@router.get("/workspace/{workspace_id}")
async def get_workspace_costs(
    workspace_id: str,
    request: Request,
    start_date: Optional[str] = Query(default=None, description="ISO date string"),
    end_date: Optional[str] = Query(default=None, description="ISO date string"),
    model: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    _=require_scope("costs:read"),
):
    """Get costs for a specific workspace with optional filters."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {
        "account_id": account_id,
        "workspace_id": workspace_id,
    }

    # Date range filter
    date_filter: Dict[str, Any] = {}
    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)
    if parsed_start:
        date_filter["gte"] = parsed_start
    if parsed_end:
        date_filter["lte"] = parsed_end
    if date_filter:
        where["created_at"] = date_filter

    if model:
        where["model"] = model
    if user_id:
        where["user_id"] = user_id

    costs = await prisma_client.db.alchemi_costtrackingtable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    total_cost = sum(c.cost for c in costs)

    return {
        "costs": costs,
        "total_cost": total_cost,
        "count": len(costs),
    }


@router.get("/user/{user_id}")
async def get_user_costs(
    user_id: str,
    request: Request,
    start_date: Optional[str] = Query(default=None, description="ISO date string"),
    end_date: Optional[str] = Query(default=None, description="ISO date string"),
    workspace_id: Optional[str] = Query(default=None),
    _=require_scope("costs:read"),
):
    """Get costs for a specific user."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {
        "account_id": account_id,
        "user_id": user_id,
    }

    date_filter: Dict[str, Any] = {}
    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)
    if parsed_start:
        date_filter["gte"] = parsed_start
    if parsed_end:
        date_filter["lte"] = parsed_end
    if date_filter:
        where["created_at"] = date_filter

    if workspace_id:
        where["workspace_id"] = workspace_id

    costs = await prisma_client.db.alchemi_costtrackingtable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    total_cost = sum(c.cost for c in costs)

    return {
        "costs": costs,
        "total_cost": total_cost,
        "count": len(costs),
    }


@router.get("/account")
async def get_account_costs(
    request: Request,
    start_date: Optional[str] = Query(default=None, description="ISO date string"),
    end_date: Optional[str] = Query(default=None, description="ISO date string"),
    _=require_scope("costs:read"),
):
    """Get account-level costs."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}

    date_filter: Dict[str, Any] = {}
    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)
    if parsed_start:
        date_filter["gte"] = parsed_start
    if parsed_end:
        date_filter["lte"] = parsed_end
    if date_filter:
        where["created_at"] = date_filter

    costs = await prisma_client.db.alchemi_costtrackingtable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    total_cost = sum(c.cost for c in costs)

    return {
        "costs": costs,
        "total_cost": total_cost,
        "count": len(costs),
    }


@router.get("/daily")
async def get_daily_costs(
    request: Request,
    start_date: Optional[str] = Query(default=None, description="ISO date string"),
    end_date: Optional[str] = Query(default=None, description="ISO date string"),
    workspace_id: Optional[str] = Query(default=None),
    group_by: Optional[str] = Query(default=None, description="Group by: model, user_id, workspace_id, tool"),
    _=require_scope("costs:read"),
):
    """Get daily cost breakdown with optional grouping."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Default date range: last 30 days
    parsed_start = _parse_date(start_date, datetime.utcnow() - timedelta(days=30))
    parsed_end = _parse_date(end_date, datetime.utcnow())

    # Validate group_by
    allowed_groups = {"model", "user_id", "workspace_id", "tool"}
    if group_by and group_by not in allowed_groups:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid group_by value. Allowed: {', '.join(allowed_groups)}",
        )

    # Build SQL query
    select_cols = 'DATE("created_at") as date, SUM(cost) as total_cost, COUNT(*) as request_count'
    group_cols = 'DATE("created_at")'
    order_cols = "date DESC"

    if group_by:
        select_cols = f'DATE("created_at") as date, "{group_by}", SUM(cost) as total_cost, COUNT(*) as request_count'
        group_cols = f'DATE("created_at"), "{group_by}"'
        order_cols = f"date DESC, \"{group_by}\""

    # Build WHERE clause
    conditions = ['"account_id" = $1', '"created_at" >= $2', '"created_at" <= $3']
    params: list = [account_id, parsed_start, parsed_end]

    if workspace_id:
        params.append(workspace_id)
        conditions.append(f'"workspace_id" = ${len(params)}')

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT {select_cols}
        FROM "Alchemi_CostTrackingTable"
        WHERE {where_clause}
        GROUP BY {group_cols}
        ORDER BY {order_cols}
    """

    rows = await prisma_client.db.query_raw(sql, *params)

    return {
        "daily": rows,
        "start_date": parsed_start.isoformat() if parsed_start else None,
        "end_date": parsed_end.isoformat() if parsed_end else None,
    }
