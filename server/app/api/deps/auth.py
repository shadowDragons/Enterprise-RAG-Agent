from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedPrincipal, build_principal, create_system_principal, decode_access_token
from app.core.config import get_settings
from app.db.session import get_db
from app.models import AuthUser

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    settings = get_settings()
    if not settings.auth_enabled:
        return create_system_principal()

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("未登录或 token 缺失。")

    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise _unauthorized(str(exc)) from exc

    username = str(payload.get("sub", "")).strip()
    if not username:
        raise _unauthorized("token 无效。")

    user = db.scalar(select(AuthUser).where(AuthUser.username == username))
    if user is None or not user.is_active:
        raise _unauthorized("用户不存在或已停用。")

    return build_principal(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        roles=user.roles,
        is_active=user.is_active,
    )


def require_permissions(*permissions: str):
    required_permissions = tuple(
        sorted({str(permission or "").strip() for permission in permissions if permission})
    )

    def dependency(
        current_user: AuthenticatedPrincipal = Depends(get_current_user),
    ) -> AuthenticatedPrincipal:
        missing_permissions = [
            permission
            for permission in required_permissions
            if permission not in current_user.permissions
        ]
        if missing_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"当前账号缺少权限：{', '.join(missing_permissions)}",
            )
        return current_user

    return dependency


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
