"""Enterprise route checks - replaces EnterpriseRouteChecks."""
from typing import Optional, Dict, Any, List


class AlchemiRouteChecks:
    """Route-level access control checks."""

    @staticmethod
    def enterprise_route_check(
        route: str,
        request_data: Optional[Dict[str, Any]] = None,
        user_api_key_dict: Optional[Any] = None,
        premium_user: bool = True,
    ) -> Optional[Dict[str, Any]]:
        return None

    @staticmethod
    def check_allowed_routes(
        route: str,
        allowed_routes: Optional[List[str]] = None,
    ) -> bool:
        if allowed_routes is None or len(allowed_routes) == 0:
            return True
        return route in allowed_routes or any(
            route.startswith(allowed) for allowed in allowed_routes
        )
