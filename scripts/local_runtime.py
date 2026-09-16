"""Local configuration and backend launcher; all mutable state stays in .runtime."""
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


def runtime_python() -> str:
    """Prefer the project AI interpreter when it has the web dependencies.

    The global Windows Python on this machine has a broken Torchvision binary;
    selecting an interpreter is safer than starting a server that reports
    ``AI_ERROR`` after the first frame.
    """
    candidate = ROOT / ".venv-ai" / "Scripts" / "python.exe"
    if candidate.is_file():
        probe = subprocess.run([str(candidate), "-c", "import fastapi, uvicorn"],
                               capture_output=True, check=False)
        if probe.returncode == 0:
            return str(candidate)
    return sys.executable


def environment():
    RUNTIME.mkdir(exist_ok=True)
    path = RUNTIME / "phase4.env"
    if not path.exists():
        key = secrets.token_urlsafe(32)
        values = {
            "VISIONGUARD_DATABASE_URL": "sqlite:///" + (RUNTIME / "phase4.sqlite3").as_posix(),
            "VISIONGUARD_JWT_SECRET": secrets.token_urlsafe(48),
            "SURAKSH_EDGE_INGEST_KEY": key,
            "VISIONGUARD_EDGE_INGEST_KEY": hashlib.sha256(key.encode()).hexdigest(),
            "VISIONGUARD_DEMO_RUNTIME_ONLY": "true",
            "VISIONGUARD_DEMO_MODE": "true",
            "VISIONGUARD_DEMO_MEDIA_DIR": str(ROOT / "demo-media"),
        }
        path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    values = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line)
    return {"OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "OMP_THREAD_LIMIT": "2",
            "OPENCV_FOR_THREADS_NUM": "1", **os.environ, **values}


if __name__ == "__main__":
    env = environment()
    python = runtime_python()
    subprocess.run([python, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend", env=env, check=True)
    if "--migrate-only" not in sys.argv:
        subprocess.run([python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT / "backend", env=env, check=True)
