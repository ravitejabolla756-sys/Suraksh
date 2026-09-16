import sys
import os
import secrets
import hashlib
import tempfile
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
# Never point destructive schema setup at a developer/runtime database.
_test_dir = tempfile.TemporaryDirectory(prefix="suraksh-tests-", dir=BACKEND_ROOT)
os.environ["VISIONGUARD_DATABASE_URL"] = "sqlite:///" + str(Path(_test_dir.name) / "tests.db")
os.environ["VISIONGUARD_JWT_SECRET"] = secrets.token_urlsafe(32)
os.environ["SURAKSH_EDGE_INGEST_KEY"] = secrets.token_urlsafe(32)
os.environ["VISIONGUARD_EDGE_INGEST_KEY"] = hashlib.sha256(os.environ["SURAKSH_EDGE_INGEST_KEY"].encode()).hexdigest()
os.environ["VISIONGUARD_DEMO_RUNTIME_ONLY"] = "false"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.database import Base, SessionLocal, engine  # noqa: E402
from app.services.seed import seed_demo  # noqa: E402


def pytest_sessionstart(session):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_demo(db)
    finally:
        db.close()


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    _test_dir.cleanup()
