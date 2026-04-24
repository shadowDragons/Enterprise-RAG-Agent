from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps.auth import get_current_user
from app.core.auth import build_principal, create_access_token, verify_password
from app.db.session import get_db
from app.models import AuthUser
from app.schemas.auth import AuthLoginRequest, AuthTokenResponse, CurrentUser, to_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    payload: AuthLoginRequest,
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    username = payload.username.strip()
    user = db.scalar(select(AuthUser).where(AuthUser.username == username))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal = build_principal(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        roles=user.roles,
        is_active=user.is_active,
    )
    access_token, expires_at = create_access_token(username=user.username)
    return AuthTokenResponse(
        access_token=access_token,
        expires_at=expires_at,
        user=to_current_user(principal),
    )


@router.get("/me", response_model=CurrentUser)
async def me(current_user=Depends(get_current_user)) -> CurrentUser:
    return to_current_user(current_user)
