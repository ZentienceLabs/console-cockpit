from fastapi import Request


def get_litellm_virtual_key(request: Request) -> str:
    """
    Extract and format API key from request headers.
    Prioritizes x-alchemi-api-key, then x-litellm-api-key, then Authorization header.

    Vertex JS SDK uses `Authorization` header, we use `x-alchemi-api-key` (or
    legacy `x-litellm-api-key`) to pass the virtual key.
    """
    alchemi_api_key = request.headers.get("x-alchemi-api-key")
    if alchemi_api_key:
        return f"Bearer {alchemi_api_key}"
    litellm_api_key = request.headers.get("x-litellm-api-key")
    if litellm_api_key:
        return f"Bearer {litellm_api_key}"
    return request.headers.get("Authorization", "")

