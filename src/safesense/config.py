from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("SAFESENSE_DATA_DIR", ROOT / "data"))
DATABASE_URL = os.getenv("SAFESENSE_DATABASE_URL", f"sqlite:///{DATA_DIR / 'safesense.db'}")
STALE_AFTER_SECONDS = int(os.getenv("SAFESENSE_CSI_STALE_AFTER_SECONDS", "20"))
