import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "viewer": {
        "assistant:read",
        "chat:write",
        "document:read",
        "knowledge_base:read",
        "session:read",
        "session:write",
        "system:read",
    },
    "operator": {
        "assistant:read",
        "chat:write",
        "document:read",
        "document:write",
        "job:read",
        "job:write",
        "knowledge_base:read",
        "knowledge_base:write",
        "review:read",
        "review:write",
        "session:read",
        "session:write",
        "system:read",
        "system:write",
    },
    "admin": {
        "assistant:read",
        "assistant:write",
        "chat:write",
        "document:read",
        "document:write",
        "job:read",
        "job:write",
        "knowledge_base:read",
        "knowledge_base:write",
        "review:read",
        "review:write",
        "session:read",
        "session:write",
        "system:read",
        "system:write",
    },
}
ALL_PERMISSIONS = sorted(
    {permission for permissions in ROLE_PERMISSIONS.values() for permission in permissions}
)
PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 390000


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: str
    username: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    is_active: bool = True


def normalize_roles(roles: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    for role in roles or []:
        normalized = str(role or "").strip().lower()
        if normalized and normalized in ROLE_PERMISSIONS and normalized not in result:
            result.append(normalized)
    return result or ["viewer"]


def resolve_permissions(roles: list[str] | tuple[str, ...] | None) -> list[str]:
    permissions: set[str] = set()
    for role in normalize_roles(roles):
        permissions.update(ROLE_PERMISSIONS[role])
    return sorted(permissions)


def build_principal(
    *,
    user_id: str,
    username: str,
    display_name: str,
    roles: list[str] | tuple[str, ...] | None,
    is_active: bool = True,
) -> AuthenticatedPrincipal:
    normalized_roles = normalize_roles(roles)
    return AuthenticatedPrincipal(
        user_id=user_id,
        username=username,
        display_name=display_name,
        roles=normalized_roles,
        permissions=resolve_permissions(normalized_roles),
        is_active=is_active,
    )


def create_system_principal() -> AuthenticatedPrincipal:
    return build_principal(
        user_id="system-admin",
        username="system",
        display_name="系统管理员",
        roles=["admin"],
        is_active=True,
    )


def hash_password(password: str, *, salt_hex: str | None = None) -> str:
    password_text = str(password or "")
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password_text.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return (
        f"{PASSWORD_HASH_PREFIX}${PASSWORD_HASH_ITERATIONS}"
        f"${salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, expected_digest = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != PASSWORD_HASH_PREFIX:
        return False
    try:
        iterations = int(iterations_text)
    except ValueError:
        return False
    computed_digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    ).hex()
    return hmac.compare_digest(computed_digest, expected_digest)


def create_access_token(
    *,
    username: str,
    expires_minutes: int | None = None,
) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.auth_access_token_expire_minutes
    )
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "exp": int(expires_at.timestamp()),
    }
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = _sign(signing_input)
    token = f"{signing_input}.{_b64url_encode(signature)}"
    return token, expires_at


def decode_access_token(token: str) -> dict:
    segments = str(token or "").split(".")
    if len(segments) != 3:
        raise ValueError("token 格式无效。")
    header_segment, payload_segment, signature_segment = segments
    signing_input = f"{header_segment}.{payload_segment}"
    expected_signature = _sign(signing_input)
    actual_signature = _b64url_decode(signature_segment)
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise ValueError("token 签名校验失败。")
    payload = json.loads(_b64url_decode(payload_segment))
    if not isinstance(payload, dict):
        raise ValueError("token payload 无效。")
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        raise ValueError("token 缺少过期时间。")
    if datetime.now(timezone.utc).timestamp() >= expires_at:
        raise ValueError("token 已过期。")
    return payload


def _sign(signing_input: str) -> bytes:
    settings = get_settings()
    return hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")
