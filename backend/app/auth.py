from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Depends, Header

from .config import jwt_secret, token_hours
from .database import connect
from .errors import fail

hasher = PasswordHasher()

USER_PROFILE = """SELECT u.id,u.username,u.name,u.department_id,d.name department_name,
                         u.role,u.is_active,u.created_at
                  FROM users u LEFT JOIN departments d ON d.id=u.department_id"""


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError):
        return False


def make_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=token_hours())
    return jwt.encode({"sub": str(user_id), "exp": expires}, jwt_secret(), algorithm="HS256")


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        fail(401, "UNAUTHORIZED", "请先登录")
    try:
        payload = jwt.decode(authorization[7:], jwt_secret(), algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        fail(401, "UNAUTHORIZED", "登录已过期或令牌无效")
    db = connect()
    try:
        row = db.execute(USER_PROFILE + " WHERE u.id=?", (user_id,)).fetchone()
    finally:
        db.close()
    if not row or not row["is_active"]:
        fail(401, "UNAUTHORIZED", "账号已停用或不存在")
    return dict(row)


def admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "ADMIN":
        fail(403, "FORBIDDEN", "需要管理员权限")
    return user
