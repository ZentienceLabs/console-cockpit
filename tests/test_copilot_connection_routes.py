from litellm.proxy.proxy_server import app


def test_copilot_connection_routes_registered() -> None:
    paths = {route.path for route in app.routes}

    required = {
        "/copilot/connections/mcp",
        "/copilot/connections/openapi",
        "/copilot/connections/integrations",
        "/copilot/connections/integrations/{integration_id}",
        "/copilot/connections/integration-catalog",
        "/copilot/connections/enablements",
    }

    missing = sorted(required.difference(paths))
    assert not missing, f"Missing connection routes: {missing}"
