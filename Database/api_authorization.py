import json
import hmac
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, TypedDict

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)
ROLE_CONFIG_PATH = Path(__file__).with_name("role_permissions.json")


class RoleConfig(TypedDict):
    api_key_env: str
    permissions: list[str]


@lru_cache(maxsize=1)
def load_role_config() -> dict[str, RoleConfig]:
    try:
        config: Any = json.loads(ROLE_CONFIG_PATH.read_text(encoding="utf-8"))
    except OSError:
        logger.exception("Could not read role configuration: %s", ROLE_CONFIG_PATH)
        raise HTTPException(
            status_code=503,
            detail="Role configuration is unavailable",
        ) from None
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in role configuration: %s", ROLE_CONFIG_PATH)
        raise HTTPException(
            status_code=503,
            detail="Role configuration is invalid",
        ) from None

    roles = config.get("roles") if isinstance(config, dict) else None
    if not isinstance(roles, dict) or not {"admin", "llm"} <= roles.keys():
        logger.error("Role configuration must define admin and llm roles")
        raise HTTPException(
            status_code=503,
            detail="Role configuration is invalid",
        )

    validated_roles: dict[str, RoleConfig] = {}
    for role_name, role_config in roles.items():
        if (
            not isinstance(role_name, str)
            or not role_name
            or not isinstance(role_config, dict)
        ):
            logger.error("Role configuration contains an invalid role entry")
            raise HTTPException(
                status_code=503,
                detail="Role configuration is invalid",
            )

        key_env = role_config.get("api_key_env")
        permissions = role_config.get("permissions")
        if (
            not isinstance(key_env, str)
            or not key_env
            or not isinstance(permissions, list)
            or not permissions
            or any(
                not isinstance(permission, str) or not permission
                for permission in permissions
            )
        ):
            logger.error("Role configuration is invalid for role %s", role_name)
            raise HTTPException(
                status_code=503,
                detail="Role configuration is invalid",
            )
        validated_roles[role_name] = {
            "api_key_env": key_env,
            "permissions": permissions,
        }

    if "*" not in validated_roles["admin"]["permissions"]:
        logger.error("Admin role must have wildcard permission")
        raise HTTPException(
            status_code=503,
            detail="Role configuration is invalid",
        )
    return validated_roles


def get_api_role(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    roles = load_role_config()
    keys = {
        role_name: os.getenv(role_config["api_key_env"])
        for role_name, role_config in roles.items()
    }
    configured_keys = [key for key in keys.values() if key]
    if (
        len(configured_keys) != len(keys)
        or len(set(configured_keys)) != len(configured_keys)
    ):
        logger.error("API authorization requires distinct keys for every role")
        raise HTTPException(
            status_code=503,
            detail="API authorization is not configured",
        )
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Bearer API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    provided_key = credentials.credentials
    provided_key = credentials.credentials
    for role_name, api_key in keys.items():
        if api_key is not None and hmac.compare_digest(provided_key, api_key):
            return role_name
    raise HTTPException(
        status_code=401,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_permission(permission: str) -> Callable[..., None]:
    def permission_dependency(role: str = Depends(get_api_role)) -> None:
        role_config = load_role_config()[role]
        role_permissions = role_config["permissions"]
        if "*" not in role_permissions and permission not in role_permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permission required: {permission}",
            )

    return permission_dependency
