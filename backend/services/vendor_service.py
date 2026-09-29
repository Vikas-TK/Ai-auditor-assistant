from typing import List, Optional

from sqlalchemy.orm import Session

from backend.models import Vendor

VENDOR_ID_PREFIX = "VND-"
VENDOR_ID_START = 1001


def generate_next_vendor_id(db: Session) -> str:
    existing_ids = [v.vendor_id for v in db.query(Vendor.vendor_id).all()]
    max_suffix = VENDOR_ID_START - 1
    for vendor_id in existing_ids:
        if vendor_id.startswith(VENDOR_ID_PREFIX):
            try:
                suffix = int(vendor_id[len(VENDOR_ID_PREFIX):])
                max_suffix = max(max_suffix, suffix)
            except ValueError:
                continue
    return f"{VENDOR_ID_PREFIX}{max_suffix + 1}"


def create_vendor(
    db: Session,
    vendor_name: str,
    department: Optional[str] = None,
    category: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Vendor:
    vendor = Vendor(
        vendor_id=generate_next_vendor_id(db),
        vendor_name=vendor_name,
        department=department,
        category=category,
        created_by=created_by,
        is_seed_vendor=False,
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor


def list_vendors(db: Session) -> List[Vendor]:
    return db.query(Vendor).order_by(Vendor.vendor_id).all()


def get_vendor_by_id(db: Session, vendor_id: str) -> Optional[Vendor]:
    return db.query(Vendor).filter(Vendor.vendor_id == vendor_id).first()
