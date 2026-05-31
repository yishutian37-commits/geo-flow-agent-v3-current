import os
import sys
import traceback
from pathlib import Path
from typing import TextIO

import uvicorn


_BOOT_LOG_PATH: Path | None = None
_RUNTIME_LOG_FILE: TextIO | None = None


def _log_boot(message: str) -> None:
    if _BOOT_LOG_PATH is None:
        return

    with _BOOT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def _as_sqlite_url(prefix: str, db_path: Path) -> str:
    return f"{prefix}:///{db_path.as_posix()}"


def configure_desktop_environment() -> tuple[str, int]:
    global _BOOT_LOG_PATH, _RUNTIME_LOG_FILE

    host = os.getenv("GEO_DESKTOP_HOST", "127.0.0.1")
    port = int(os.getenv("GEO_DESKTOP_PORT", "8000"))

    data_dir = Path(os.getenv("GEO_USER_DATA_DIR", Path.cwd() / "desktop-data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    (data_dir / "models").mkdir(parents=True, exist_ok=True)
    _BOOT_LOG_PATH = data_dir / "logs" / "backend-boot.log"
    _RUNTIME_LOG_FILE = (data_dir / "logs" / "backend-runtime.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = _RUNTIME_LOG_FILE
    sys.stderr = _RUNTIME_LOG_FILE
    _log_boot(f"[desktop] data_dir={data_dir}")

    db_path = data_dir / "geoflow.db"
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("DEBUG", "False")
    os.environ.setdefault("DESKTOP_MODE", "1")
    os.environ.setdefault("DATABASE_URL", _as_sqlite_url("sqlite+aiosqlite", db_path))
    os.environ.setdefault("SYNC_DATABASE_URL", _as_sqlite_url("sqlite", db_path))
    os.environ.setdefault("GEO_LLM_REGISTRY_PATH", str(data_dir / "models" / "llm_registry.json"))
    os.environ.setdefault(
        "CORS_ALLOW_ORIGIN_REGEX",
        r"^(app://.*|file://.*|http://localhost:\d+|http://127\.0\.0\.1:\d+)$",
    )
    _log_boot(f"[desktop] bind={host}:{port}")

    return host, port


if __name__ == "__main__":
    try:
        bind_host, bind_port = configure_desktop_environment()
        _log_boot("[desktop] importing app.main")
        from app.main import app

        _log_boot("[desktop] imported app.main")
        _log_boot("[desktop] starting uvicorn")
        uvicorn.run(app, host=bind_host, port=bind_port, log_config=None, access_log=False)
    except Exception:
        _log_boot("[desktop] startup failed")
        _log_boot(traceback.format_exc())
        raise
