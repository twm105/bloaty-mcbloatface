"""
Authentication service package.

Provides pluggable authentication with support for:
- Local password-based auth (current)
- Keycloak/OAuth (future)

Usage:
    from app.services.auth import get_auth_provider
    from app.services.auth.dependencies import get_current_user, require_auth_page

    # In routes:
    @router.get("/protected")
    async def protected_route(user: User = Depends(get_current_user)):
        ...
"""
from app.services.auth.base import AuthProvider
from app.services.auth.local_provider import local_auth_provider


def get_auth_provider() -> AuthProvider:
    """
    Factory function to get the configured auth provider.

    Currently returns LocalAuthProvider. In future, this can be
    configured via environment variable to return KeycloakAuthProvider.
    """
    # Future: Check AUTH_PROVIDER env var and return appropriate provider
    # if settings.auth_provider == "keycloak":
    #     return keycloak_auth_provider
    return local_auth_provider


__all__ = [
    "AuthProvider",
    "get_auth_provider",
    "local_auth_provider",
]
