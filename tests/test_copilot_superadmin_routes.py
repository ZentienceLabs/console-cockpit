from litellm.proxy.proxy_server import app


def test_copilot_superadmin_routes_registered() -> None:
    paths = {route.path for route in app.routes}

    required = {
        "/copilot/super-admin/subscription-plans",
        "/copilot/super-admin/accounts/{account_id}/setup",
        "/copilot/super-admin/accounts/{account_id}/entitlements",
        "/copilot/super-admin/accounts/{account_id}/quotas",
        "/copilot/super-admin/feature-catalog",
        "/copilot/super-admin/platform-catalog",
        "/copilot/super-admin/config/providers",
        "/copilot/super-admin/config/models",
        "/copilot/super-admin/config/media-models",
        "/copilot/super-admin/support/tickets",
        "/copilot/super-admin/platform-notification-templates",
    }

    missing = sorted(required.difference(paths))
    assert not missing, f"Missing super-admin routes: {missing}"
