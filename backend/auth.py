import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import get_db
from backend.models import RefreshToken

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# There's no credential-based login — signing in means picking (or creating) a
# vendor in the picker. Every issued token represents the same implicit identity.
SESSION_SUBJECT = "auditor"


def _utcnow():
    return datetime.now(timezone.utc)


def create_access_token() -> str:
    expire = _utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": SESSION_SUBJECT, "type": "access", "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(db: Session) -> str:
    jti = uuid.uuid4().hex
    expire = _utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db.add(RefreshToken(jti=jti, expires_at=expire))
    db.commit()

    payload = {"sub": SESSION_SUBJECT, "jti": jti, "type": "refresh", "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def rotate_refresh_token(db: Session, refresh_token: str):
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")

    jti = payload.get("jti")
    record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown refresh token")

    if record.revoked or record.expires_at.replace(tzinfo=timezone.utc) < _utcnow():
        # Reuse of an already-rotated/revoked refresh token is treated as a possible
        # token theft — revoke every other outstanding session as a precaution.
        db.query(RefreshToken).filter(RefreshToken.revoked.is_(False)).update({"revoked": True})
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired")

    new_access = create_access_token()
    new_refresh = create_refresh_token(db)

    new_jti = jwt.get_unverified_claims(new_refresh)["jti"]
    record.revoked = True
    record.replaced_by_jti = new_jti
    db.commit()

    return new_access, new_refresh


def revoke_refresh_token(db: Session, refresh_token: str):
    try:
        payload = decode_token(refresh_token)
    except HTTPException:
        return
    jti = payload.get("jti")
    record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if record:
        record.revoked = True
        db.commit()


@dataclass
class AuthedUser:
    username: str


def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> AuthedUser:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")

    return AuthedUser(username=payload.get("sub", SESSION_SUBJECT))


def resolve_vendor_context(
    x_vendor_context: Optional[str] = Header(None),
    user: AuthedUser = Depends(get_current_user),
) -> str:
    """The vendor the caller picked at sign-in (or "ALL" for the global view)."""
    return x_vendor_context if x_vendor_context else "ALL"
