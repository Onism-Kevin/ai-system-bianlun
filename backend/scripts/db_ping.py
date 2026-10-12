"""S1-1 连通性冒烟：对 dev/test/demo 三环境各执行一次 SELECT 1。

用法（在 backend/ 目录下）：
    venv\\Scripts\\python.exe scripts\\db_ping.py
输出三行结果，全部 OK 即通过；任何失败以非零退出码结束。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import ENV_SCHEMAS, Settings, database_url_for  # noqa: E402


def main() -> int:
    settings = Settings()
    print(f"MODEL_BASE_URL = {settings.model_base_url}")
    print(f"MODEL_DEFAULT  = {settings.model_default}")
    print(f"APP_ENV        = {settings.app_env}")
    print("")

    failed = 0
    for env in ("dev", "test", "demo"):
        url_obj = database_url_for(env, settings)
        engine = create_engine(url_obj, pool_pre_ping=True)  # URL 对象直传，避免字符串往返转义密码
        try:
            with engine.connect() as conn:
                version = conn.execute(text("SELECT VERSION()")).scalar_one()
            print(f"{env:<5} ({ENV_SCHEMAS[env]:<9}) SELECT 1 OK, MySQL {version}")
        except Exception as exc:  # noqa: BLE001 —— 冒烟脚本要汇总所有失败
            failed += 1
            print(f"{env:<5} ({ENV_SCHEMAS[env]:<9}) FAILED: {exc.__class__.__name__}")
        finally:
            engine.dispose()

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
