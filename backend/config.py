import os
import warnings
import secrets
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    DATA_DIR: str = os.path.join(PROJECT_ROOT, "data")
    RAW_LEDGER_PATH: str = os.path.join(DATA_DIR, "raw_ledgers", "corporate_ledger.csv")
    CLEANED_LEDGER_PATH: str = os.path.join(DATA_DIR, "raw_ledgers", "cleaned_ledger.csv")
    INVOICE_DIR: str = os.path.join(DATA_DIR, "sample_invoices")
    POLICY_DIR: str = os.path.join(DATA_DIR, "policy_documents")
    CHROMA_DB_PATH: str = os.path.join(DATA_DIR, "vector_db")
    DATABASE_PATH: str = os.path.join(DATA_DIR, "app.db")

    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    if not JWT_SECRET_KEY:
        warnings.warn(
            "JWT_SECRET_KEY not set in .env — generating an ephemeral dev-only secret. "
            "All existing sessions will be invalidated on every restart. Set JWT_SECRET_KEY in .env for stable sessions.",
            stacklevel=2
        )
        JWT_SECRET_KEY = secrets.token_hex(32)

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # --- Module 2 anomaly rule-engine tuning (defaults calibrated for the USD
    # City-of-Chicago Contracts ledger; override per active dataset via .env) ---
    # "Split / threshold-bypass": amounts landing just under a round approval limit.
    ANOMALY_APPROVAL_THRESHOLDS: list = [
        float(x) for x in os.getenv("ANOMALY_APPROVAL_THRESHOLDS", "25000,50000,100000,250000").split(",") if x.strip()
    ]
    ANOMALY_THRESHOLD_BAND: float = float(os.getenv("ANOMALY_THRESHOLD_BAND", "0.05"))
    # "Duplicate payment": same vendor + amount within N days. Ignore tiny/zero amounts
    # (master agreements, $0 placeholder rows) which otherwise collide en masse.
    ANOMALY_DUP_MIN_AMOUNT: float = float(os.getenv("ANOMALY_DUP_MIN_AMOUNT", "1000"))
    ANOMALY_DUP_WINDOW_DAYS: int = int(os.getenv("ANOMALY_DUP_WINDOW_DAYS", "2"))
    CURRENCY_SYMBOL: str = os.getenv("CURRENCY_SYMBOL", "$")

    ALLOWED_ORIGINS: list = [
        origin.strip() for origin in os.getenv(
            "ALLOWED_ORIGINS", f"http://127.0.0.1:{PORT},http://localhost:{PORT}"
        ).split(",") if origin.strip()
    ]

settings = Settings()

