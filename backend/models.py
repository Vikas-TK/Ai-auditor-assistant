from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from backend.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(String(20), unique=True, nullable=False, index=True)
    vendor_name = Column(String(255), nullable=False)
    department = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    created_by = Column(String(100), nullable=True)
    is_seed_vendor = Column(Boolean, default=False, nullable=False)


class RefreshToken(Base):
    """Tracks issued refresh tokens for rotation/revocation. There's no user
    account concept — signing in means picking a vendor in the picker, so
    these aren't tied to a users table, just to the session's jti chain."""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(String(64), unique=True, nullable=False, index=True)
    issued_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    replaced_by_jti = Column(String(64), nullable=True)
