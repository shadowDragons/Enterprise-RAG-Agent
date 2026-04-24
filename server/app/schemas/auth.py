from datetime import datetime

from pydantic import BaseModel, Field


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=255)


class CurrentUser(BaseModel):
    user_id: str
    username: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    is_active: bool


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: CurrentUser


def to_current_user(principal) -> CurrentUser:
    return CurrentUser(
        user_id=principal.user_id,
        username=principal.username,
        display_name=principal.display_name,
        roles=list(principal.roles),
        permissions=list(principal.permissions),
        is_active=principal.is_active,
    )
