from typing import Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Signing in means picking a vendor, not entering credentials.
    - Existing vendor: pass vendor_id.
    - New vendor: pass vendor_name (and optionally department/category) — it's
      created and signed into in one step.
    - Neither: signs in to the "All Vendors (Global)" aggregate view.
    """
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    department: Optional[str] = None
    category: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    vendor_id: str
    vendor_name: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class VendorCreateRequest(BaseModel):
    vendor_name: str
    department: Optional[str] = None
    category: Optional[str] = None


class VendorOut(BaseModel):
    vendor_id: str
    vendor_name: str
    department: Optional[str] = None
    category: Optional[str] = None

    class Config:
        from_attributes = True
