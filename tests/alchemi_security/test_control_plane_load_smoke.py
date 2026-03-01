import asyncio
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from alchemi.endpoints.control_plane_v1 import router as control_plane_router
from alchemi.middleware.account_middleware import AccountContextMiddleware


@pytest.mark.asyncio
async def test_me_context_concurrent_load_smoke(monkeypatch: pytest.MonkeyPatch):
    """
    Fast concurrency smoke to validate middleware + router throughput path.
    Uses /v1/me/context since it exercises auth context without DB dependency.
    """
    monkeypatch.setenv("LITELLM_MASTER_KEY", "load-test-master-key")

    app = FastAPI()
    app.add_middleware(AccountContextMiddleware)
    app.include_router(control_plane_router)

    headers = {
        "Authorization": "Bearer load-test-master-key",
        "X-Account-Id": "acc-load",
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start = time.perf_counter()
        tasks = [client.get("/v1/me/context", headers=headers) for _ in range(600)]
        responses = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start

    assert all(resp.status_code == 200 for resp in responses)
    rps = len(responses) / elapsed if elapsed > 0 else 0
    # Conservative lower bound for CI/dev environments.
    assert rps > 50, f"Load smoke throughput too low: {rps:.2f} req/s"
